/**
 * @file main.c
 * LVGL host: headless by default, Win32 GDI window with --window. The user's
 * only entry point is app_create().
 *
 * Virtual time advances only through tick/wait commands; the session owns
 * the refresh -> capture -> timeline -> diff chain. In window mode every
 * LVGL call stays on the window thread: protocol lines arrive through the
 * stdin queue, real input arrives through Win32 messages.
 */

#include "adapter.h"
#include "json.h"
#include "protocol.h"
#include "session.h"
#include "stdin_queue.h"
#include "window.h"

#include <ctype.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DISPLAY_WIDTH 800u
#define DISPLAY_HEIGHT 600u
#define DEFAULT_MAX_FRAMES 600

extern void app_create(void);

typedef struct {
    adapter_t * adapter;
    session_t session;
    /** Non-NULL only while the Win32 window is open. */
    window_t * window;
    /** Stdin reader thread used by the window main loop. */
    stdin_queue_t * stdin_queue;
} engine_t;

static void print_usage(FILE * out)
{
    fprintf(out,
            "usage: lvgl_engine --session DIR [--record|--no-record]\n"
            "                  [--live-frame] [--record-changed-only]\n"
            "                  [--diff-threshold 0-255]\n"
            "                  [--reference PNG] [--max-frames N]\n"
            "                  [--window|--headless]\n");
}

static bool only_spaces(const char * text)
{
    if(text == NULL) return true;
    while(*text != '\0') {
        if(!isspace((unsigned char)*text)) return false;
        text++;
    }
    return true;
}

/** Copy the next whitespace-delimited token. NULL when no token is left. */
static const char * next_token(const char * cursor, char * out, size_t out_size)
{
    if(cursor == NULL) return NULL;
    while(*cursor != '\0' && isspace((unsigned char)*cursor)) cursor++;
    if(*cursor == '\0') return NULL;
    size_t used = 0;
    while(*cursor != '\0' && !isspace((unsigned char)*cursor)) {
        if(used + 1u < out_size) out[used++] = *cursor;
        cursor++;
    }
    out[used] = '\0';
    return cursor;
}

static bool parse_long(const char * text, long * value)
{
    if(text == NULL || *text == '\0') return false;
    char * end = NULL;
    errno = 0;
    long parsed = strtol(text, &end, 10);
    if(end == text || errno != 0 || !only_spaces(end)) return false;
    *value = parsed;
    return true;
}

static bool parse_ulong(const char * text, unsigned long * value)
{
    if(text == NULL || *text == '\0' || *text == '-') return false;
    char * end = NULL;
    errno = 0;
    unsigned long parsed = strtoul(text, &end, 10);
    if(end == text || errno != 0 || !only_spaces(end)) return false;
    *value = parsed;
    return true;
}

static bool token_valid(const char * text)
{
    if(text == NULL) return false;
    size_t length = strlen(text);
    if(length == 0 || length > 64) return false;
    for(size_t i = 0; i < length; i++) {
        unsigned char c = (unsigned char)text[i];
        if(!(isalnum(c) || c == '_' || c == '-')) return false;
    }
    return true;
}

/** Present hook: show the refreshed framebuffer when a window is open. */
static void engine_present(void * user)
{
    engine_t * engine = (engine_t *)user;
    if(engine->window != NULL) {
        window_present(engine->window, adapter_framebuffer(engine->adapter));
    }
}

/**
 * Keep real input responsive while a virtual wait runs. The callback still
 * runs on this (the window) thread, so LVGL stays single-threaded. Returns
 * false once the window closed or Ctrl+C arrived; the caller still finishes
 * the current command and replies, then the main loop exits.
 */
static bool engine_service_window(void * user)
{
    engine_t * engine = (engine_t *)user;
    if(engine->window == NULL) return true;
    if(window_console_interrupted()) return false;
    return window_pump(engine->window);
}

static void reply_state(FILE * out, long seq, const engine_t * engine,
                        const char * extra_fields)
{
    char fields[2048];
    snprintf(fields, sizeof(fields),
             ",\"frames\":%ld,\"t_ms\":%lu,\"truncated\":%s%s",
             session_frame_count(&engine->session),
             (unsigned long)session_t_ms(&engine->session),
             session_truncated(&engine->session) ? "true" : "false",
             extra_fields != NULL ? extra_fields : "");
    protocol_reply_ok(out, seq, fields);
}

static bool handle_pointer(engine_t * engine, FILE * out,
                           const command_t * command)
{
    char action_text[16] = "";
    char x_text[32] = "";
    char y_text[32] = "";
    const char * rest = next_token(command->args, action_text,
                                   sizeof(action_text));
    rest = next_token(rest, x_text, sizeof(x_text));
    rest = next_token(rest, y_text, sizeof(y_text));
    long x = 0;
    long y = 0;
    if(rest == NULL || !only_spaces(rest) || !parse_long(x_text, &x) ||
       !parse_long(y_text, &y) || x < 0 || y < 0) {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "usage: pointer down|move|up X Y");
        return true;
    }

    pointer_action_t action;
    if(strcmp(action_text, "down") == 0) action = POINTER_DOWN;
    else if(strcmp(action_text, "move") == 0) action = POINTER_MOVE;
    else if(strcmp(action_text, "up") == 0) action = POINTER_UP;
    else {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "pointer action must be down, move or up");
        return true;
    }

    if(adapter_pointer(engine->adapter, action, (int32_t)x, (int32_t)y) != 0) {
        protocol_reply_error(out, command->seq, "input_failed",
                                 "the pointer indev is not available");
        return true;
    }

    const pointer_reply_t * pointer =
        adapter_last_pointer(engine->adapter);
    const char * hit = pointer != NULL ? pointer->hit : "";
    const char * hit_class = pointer != NULL ? pointer->hit_class : "";
    session_input_pointer(&engine->session, command->seq, "virtual",
                          action_text, x, y, hit, hit_class);

    char hit_json[1024];
    char class_json[256];
    if(json_quote(hit, hit_json, sizeof(hit_json)) != 0 ||
       json_quote(hit_class, class_json, sizeof(class_json)) != 0) {
        protocol_reply_error(out, command->seq, "input_failed",
                                 "hit name is too long");
        return true;
    }
    char extra[1400];
    snprintf(extra, sizeof(extra), ",\"hit\":%s,\"hit_class\":%s", hit_json,
             class_json);
    reply_state(out, command->seq, engine, extra);
    return true;
}

static bool handle_tick(engine_t * engine, FILE * out,
                        const command_t * command)
{
    char ms_text[32];
    const char * rest = next_token(command->args, ms_text, sizeof(ms_text));
    unsigned long ms = 0;
    if(rest == NULL || !only_spaces(rest) || !parse_ulong(ms_text, &ms)) {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "usage: tick <ms>");
        return true;
    }
    session_tick(&engine->session, (uint32_t)ms);
    reply_state(out, command->seq, engine, NULL);
    return true;
}

static bool handle_wait(engine_t * engine, FILE * out,
                        const command_t * command)
{
    char first[32];
    const char * rest = next_token(command->args, first, sizeof(first));
    if(rest == NULL) {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "usage: wait <ms> | wait frames <n>");
        return true;
    }

    if(strcmp(first, "frames") == 0) {
        char frames_text[32];
        rest = next_token(rest, frames_text, sizeof(frames_text));
        unsigned long frames = 0;
        if(rest == NULL || !only_spaces(rest) ||
           !parse_ulong(frames_text, &frames)) {
            protocol_reply_error(out, command->seq, "bad_args",
                                     "usage: wait frames <n>");
            return true;
        }
        session_wait_frames(&engine->session, frames, engine_service_window,
                            engine);
        reply_state(out, command->seq, engine, NULL);
        return true;
    }

    unsigned long ms = 0;
    if(!only_spaces(rest) || !parse_ulong(first, &ms)) {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "usage: wait <ms> | wait frames <n>");
        return true;
    }
    session_wait_ms(&engine->session, ms, engine_service_window, engine);
    reply_state(out, command->seq, engine, NULL);
    return true;
}

static bool handle_mark(engine_t * engine, FILE * out,
                        const command_t * command)
{
    char id[128];
    const char * rest = next_token(command->args, id, sizeof(id));
    if(rest == NULL || !only_spaces(rest) || !token_valid(id)) {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "usage: mark <id>");
        return true;
    }
    session_mark(&engine->session, id);
    reply_state(out, command->seq, engine, NULL);
    return true;
}

static bool handle_snapshot(engine_t * engine, FILE * out,
                            const command_t * command)
{
    char label[128];
    const char * rest = next_token(command->args, label, sizeof(label));
    if(rest == NULL || !only_spaces(rest) || !token_valid(label)) {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "usage: snapshot <label>");
        return true;
    }

    char relative[256];
    if(session_snapshot(&engine->session, label, relative,
                        sizeof(relative)) != 0) {
        protocol_reply_error(out, command->seq, "capture_failed",
                                 "cannot write the snapshot PNG");
        return true;
    }

    char file_json[512];
    if(json_quote(relative, file_json, sizeof(file_json)) != 0) {
        protocol_reply_error(out, command->seq, "capture_failed",
                                 "snapshot path is too long");
        return true;
    }
    char extra[600];
    snprintf(extra, sizeof(extra), ",\"file\":%s", file_json);
    reply_state(out, command->seq, engine, extra);
    return true;
}

static bool handle_key(engine_t * engine, FILE * out,
                       const command_t * command)
{
    char action[16] = "";
    char code_text[32] = "";
    char key_name[64] = "";
    const char * rest = next_token(command->args, action, sizeof(action));
    rest = next_token(rest, code_text, sizeof(code_text));
    rest = next_token(rest, key_name, sizeof(key_name));
    bool valid_action = strcmp(action, "press") == 0 ||
                        strcmp(action, "release") == 0;
    unsigned long key_code = 0;
    if(rest == NULL || !only_spaces(rest) || !valid_action ||
       !parse_ulong(code_text, &key_code) || !token_valid(key_name)) {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "usage: key press|release <code> <name>");
        return true;
    }

    key_action_t key_action = strcmp(action, "press") == 0
                                      ? KEY_PRESS
                                      : KEY_RELEASE;
    if(adapter_key(engine->adapter, key_action,
                       (uint32_t)key_code) != 0) {
        protocol_reply_error(out, command->seq, "input_failed",
                                 "the keypad indev did not read the key");
        return true;
    }

    session_input_key(&engine->session, command->seq, "virtual", action,
                      key_name, true);
    char key_json[256];
    if(json_quote(key_name, key_json, sizeof(key_json)) != 0) {
        protocol_reply_error(out, command->seq, "input_failed",
                                 "key name is too long");
        return true;
    }
    char extra[320];
    snprintf(extra, sizeof(extra), ",\"delivered\":true,\"key\":%s", key_json);
    reply_state(out, command->seq, engine, extra);
    return true;
}

static bool handle_encoder(engine_t * engine, FILE * out,
                           const command_t * command)
{
    char action[16] = "";
    char diff_text[32] = "";
    const char * rest = next_token(command->args, action, sizeof(action));
    rest = next_token(rest, diff_text, sizeof(diff_text));
    long diff = 0;
    if(rest == NULL || !only_spaces(rest) || strcmp(action, "turn") != 0 ||
       !parse_long(diff_text, &diff) || diff < -32768 || diff > 32767) {
        protocol_reply_error(out, command->seq, "bad_args",
                                 "usage: encoder turn <diff -32768..32767>");
        return true;
    }

    if(adapter_encoder(engine->adapter, (int32_t)diff) != 0) {
        protocol_reply_error(out, command->seq, "input_failed",
                                 "the encoder indev did not read the turn");
        return true;
    }

    session_input_encoder(&engine->session, command->seq, "virtual", diff);
    reply_state(out, command->seq, engine, ",\"delivered\":true");
    return true;
}

static const char * pointer_action_name(window_pointer_action_t action)
{
    switch(action) {
        case WINDOW_POINTER_DOWN: return "down";
        case WINDOW_POINTER_UP: return "up";
        default: return "move";
    }
}

/**
 * Real OS input callback. It runs on the window thread, inside the message
 * pump, so calling LVGL here keeps the single-thread rule. Down/up and key
 * events also run timers and repaint so the human sees the result without
 * waiting for a virtual tick; drag moves repaint too.
 */
static void engine_real_input(void * user, const window_event_t * event)
{
    engine_t * engine = (engine_t *)user;
    bool repaint = false;

    if(event->kind == WINDOW_EVENT_POINTER) {
        pointer_action_t action = POINTER_MOVE;
        if(event->action == WINDOW_POINTER_DOWN) action = POINTER_DOWN;
        else if(event->action == WINDOW_POINTER_UP) action = POINTER_UP;

        if(adapter_real_pointer(engine->adapter, action, event->x,
                                    event->y) == 0) {
            /* Hover moves are delivered to LVGL but not written to the
             * timeline; pressed moves carry drag evidence. */
            if(action != POINTER_MOVE || event->pressed) {
                const pointer_reply_t * reply =
                    adapter_last_real_pointer(engine->adapter);
                session_input_pointer(
                    &engine->session, -1, "real",
                    pointer_action_name(event->action), event->x, event->y,
                    reply != NULL ? reply->hit : "",
                    reply != NULL ? reply->hit_class : "");
            }
        }
        repaint = action != POINTER_MOVE || event->pressed;
    }
    else if(event->kind == WINDOW_EVENT_KEY) {
        key_action_t action =
            event->pressed ? KEY_PRESS : KEY_RELEASE;
        int delivered = adapter_real_key(engine->adapter, action,
                                             event->key);
        session_input_key(&engine->session, -1, "real",
                          event->pressed ? "press" : "release",
                          event->key_name != NULL ? event->key_name : "",
                          delivered == 0);
        repaint = true;
    }

    if(repaint) {
        adapter_timer_handler(engine->adapter);
        adapter_refresh(engine->adapter);
        engine_present(engine);
    }
}

/** Execute one protocol line. Returns false when the session should end. */
static bool process_command(engine_t * engine, FILE * out, char * line)
{
    command_t command;
    if(!protocol_parse(line, &command)) {
        protocol_reply_error(out, 0, "bad_command",
                                 "expected <seq> <verb> [args]");
        return true;
    }

    if(strcmp(command.verb, "pointer") == 0) {
        return handle_pointer(engine, out, &command);
    }
    if(strcmp(command.verb, "tick") == 0) {
        return handle_tick(engine, out, &command);
    }
    if(strcmp(command.verb, "wait") == 0) {
        return handle_wait(engine, out, &command);
    }
    if(strcmp(command.verb, "mark") == 0) {
        return handle_mark(engine, out, &command);
    }
    if(strcmp(command.verb, "snapshot") == 0) {
        return handle_snapshot(engine, out, &command);
    }
    if(strcmp(command.verb, "key") == 0) {
        return handle_key(engine, out, &command);
    }
    if(strcmp(command.verb, "encoder") == 0) {
        return handle_encoder(engine, out, &command);
    }
    if(strcmp(command.verb, "quit") == 0) {
        session_end(&engine->session);
        reply_state(out, command.seq, engine, NULL);
        return false;
    }
    protocol_reply_error(out, command.seq, "unknown_command",
                             "command is not implemented");
    return true;
}

/**
 * Window main loop: drain queued protocol lines, pump Win32 messages, and
 * wait briefly for either. Every LVGL call stays on this thread.
 */
static void run_window_loop(engine_t * engine, FILE * out)
{
    bool eof = false;

    while(!eof) {
        for(;;) {
            bool line_eof = false;
            char * line = stdin_queue_pop(engine->stdin_queue, &line_eof);
            if(line == NULL) {
                if(line_eof) eof = true;
                break;
            }
            bool keep_running = process_command(engine, out, line);
            free(line);
            if(!keep_running) return;
        }
        if(eof) break;

        if(!window_pump(engine->window)) break;
        if(window_console_interrupted()) break;
        stdin_queue_wait(engine->stdin_queue, 5);
    }
}

/** Window title names the session so FindWindow can target one engine. */
static void session_window_title(const char * session_dir,
                                 char * out,
                                 size_t out_size)
{
    const char * base = session_dir;
    for(const char * cursor = session_dir; *cursor != '\0'; cursor++) {
        if(*cursor == '/' || *cursor == '\\') base = cursor + 1;
    }
    snprintf(out, out_size, "lvgl_engine - %s",
             base[0] != '\0' ? base : "session");
}

int main(int argc, char ** argv)
{
    const char * session_dir = NULL;
    const char * reference_path = NULL;
    long diff_threshold = 10;
    long max_frames = DEFAULT_MAX_FRAMES;
    bool record = false;
    bool live_frame = false;
    bool record_changed_only = false;
    bool window_requested = false;

    for(int i = 1; i < argc; i++) {
        if(strcmp(argv[i], "--session") == 0 && i + 1 < argc) {
            session_dir = argv[++i];
        }
        else if(strcmp(argv[i], "--reference") == 0 && i + 1 < argc) {
            reference_path = argv[++i];
        }
        else if(strcmp(argv[i], "--diff-threshold") == 0 && i + 1 < argc) {
            if(!parse_long(argv[++i], &diff_threshold) || diff_threshold < 0 ||
               diff_threshold > 255) {
                fprintf(stderr,
                        "[engine] --diff-threshold must be 0..255\n");
                return 2;
            }
        }
        else if(strcmp(argv[i], "--max-frames") == 0 && i + 1 < argc) {
            if(!parse_long(argv[++i], &max_frames) || max_frames < 0) {
                fprintf(stderr, "[engine] --max-frames must be >= 0\n");
                return 2;
            }
        }
        else if(strcmp(argv[i], "--record") == 0) {
            record = true;
        }
        else if(strcmp(argv[i], "--no-record") == 0) {
            record = false;
        }
        else if(strcmp(argv[i], "--live-frame") == 0) {
            live_frame = true;
        }
        else if(strcmp(argv[i], "--record-changed-only") == 0) {
            record_changed_only = true;
        }
        else if(strcmp(argv[i], "--window") == 0) {
            window_requested = true;
        }
        else if(strcmp(argv[i], "--headless") == 0) {
            window_requested = false;
        }
        else if(strcmp(argv[i], "--help") == 0) {
            print_usage(stdout);
            return 0;
        }
        else {
            fprintf(stderr, "[engine] unknown argument: %s\n", argv[i]);
            print_usage(stderr);
            return 2;
        }
    }

    if(session_dir == NULL) {
        fprintf(stderr, "[engine] --session is required\n");
        print_usage(stderr);
        return 2;
    }

    /* Unbuffered stdout matters beyond latency: MinGW keeps pipes fully
     * buffered despite _IOLBF, so user printf() from an event handler could
     * stay invisible in engine.log until the process exits. */
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    bool window_supported = window_requested && window_available();
    adapter_t * adapter = adapter_create(DISPLAY_WIDTH,
                                                 DISPLAY_HEIGHT,
                                                 window_supported);
    if(adapter == NULL) {
        fprintf(stderr, "[engine] failed to create the LVGL display\n");
        return 2;
    }

    uint8_t * reference_pixels = NULL;
    uint32_t reference_width = 0;
    uint32_t reference_height = 0;
    if(reference_path != NULL) {
        if(adapter_load_png(reference_path, &reference_pixels,
                                &reference_width, &reference_height) != 0) {
            fprintf(stderr, "[engine] cannot read reference %s\n",
                    reference_path);
            adapter_destroy(adapter);
            return 2;
        }
        if(reference_width != DISPLAY_WIDTH ||
           reference_height != DISPLAY_HEIGHT) {
            fprintf(stderr,
                    "[engine] reference is %ux%u, expected %ux%u\n",
                    reference_width, reference_height, DISPLAY_WIDTH,
                    DISPLAY_HEIGHT);
            adapter_free_pixels(reference_pixels);
            adapter_destroy(adapter);
            return 2;
        }
    }

    engine_t engine;
    memset(&engine, 0, sizeof(engine));
    engine.adapter = adapter;

    session_config_t session_config;
    memset(&session_config, 0, sizeof(session_config));
    session_config.adapter = adapter;
    session_config.session_dir = session_dir;
    session_config.width = DISPLAY_WIDTH;
    session_config.height = DISPLAY_HEIGHT;
    session_config.record = record;
    session_config.live = live_frame;
    session_config.record_changed_only = record_changed_only;
    session_config.max_frames = max_frames;
    session_config.diff_threshold = (int)diff_threshold;
    session_config.reference = reference_pixels;
    session_config.reference_width = reference_width;
    session_config.reference_height = reference_height;
    session_config.present = engine_present;
    session_config.present_user = &engine;
    session_init(&engine.session, &session_config);

    if(window_requested) {
        char title[256];
        session_window_title(session_dir, title, sizeof(title));
        engine.window = window_create(DISPLAY_WIDTH,
                                          DISPLAY_HEIGHT, title,
                                          engine_real_input, &engine);
        if(engine.window == NULL) {
            fprintf(stderr,
                    "[engine] window unavailable; continuing headless\n");
        }
        else {
            engine.stdin_queue = stdin_queue_start();
            if(engine.stdin_queue == NULL) {
                fprintf(stderr,
                        "[engine] cannot start the stdin reader; "
                        "closing the window and continuing headless\n");
                window_destroy(engine.window);
                engine.window = NULL;
            }
            else {
                window_install_ctrl_handler();
            }
        }
    }

    app_create();
    session_refresh_frame(&engine.session);

    const adapter_info_t * info = adapter_info(adapter);
    const char * mode = engine.window != NULL ? "window" : "headless";
    fprintf(stderr,
            "[engine] lvgl=%s adapter=%s mode=%s display=%ux%u record=%s "
            "changed_only=%s\n",
            info->lvgl_version, info->adapter_name, mode,
            info->width, info->height, record ? "on" : "off",
            record_changed_only ? "on" : "off");

    const char * capabilities =
        record ? "[\"pointer\",\"key\",\"encoder\",\"tick\",\"wait\","
                 "\"snapshot\",\"mark\",\"record\"]"
               : "[\"pointer\",\"key\",\"encoder\",\"tick\",\"wait\","
                 "\"snapshot\",\"mark\"]";
    protocol_ready(stdout, "lvgl-ai-engine-v1", info->lvgl_version,
                       info->lvgl_src, info->width, info->height, mode,
                       info->adapter_name, session_frame_count(&engine.session),
                       max_frames, session_truncated(&engine.session),
                       capabilities);

    if(engine.window != NULL) {
        run_window_loop(&engine, stdout);
    }
    else {
        char line[1024];
        while(fgets(line, sizeof(line), stdin) != NULL) {
            if(!process_command(&engine, stdout, line)) break;
        }
    }

    session_end(&engine.session);
    stdin_queue_free(engine.stdin_queue);
    window_destroy(engine.window);
    session_close(&engine.session);
    adapter_free_pixels(reference_pixels);
    adapter_destroy(adapter);
    return 0;
}
