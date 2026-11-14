cmake_minimum_required(VERSION 3.20)
project(lvgl_engine C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(NOT DEFINED LVGL_AI_LVGL_SRC OR LVGL_AI_LVGL_SRC STREQUAL "")
    message(FATAL_ERROR "LVGL_AI_LVGL_SRC is required")
endif()

# The Python layer passes native Windows paths. Normalize them before GLOB:
# CONFIGURE_DEPENDS writes the pattern into VerifyGlobs.cmake, where
# backslashes are parsed as escape sequences.
file(TO_CMAKE_PATH "${LVGL_AI_LVGL_SRC}" LVGL_AI_LVGL_SRC)

# LVGL 9.6 keeps public headers in include/lvgl; 9.1-9.5 keep lvgl.h at the
# source root. Accept both layouts; the lvgl target exports the right includes.
if(NOT EXISTS "${LVGL_AI_LVGL_SRC}/include/lvgl/lvgl.h"
   AND NOT EXISTS "${LVGL_AI_LVGL_SRC}/lvgl.h")
    message(FATAL_ERROR "LVGL source not found at ${LVGL_AI_LVGL_SRC}")
endif()

if(NOT DEFINED LVGL_AI_USER_APP_DIR OR NOT EXISTS "${LVGL_AI_USER_APP_DIR}")
    message(FATAL_ERROR "user/app directory not found: ${LVGL_AI_USER_APP_DIR}")
endif()
file(TO_CMAKE_PATH "${LVGL_AI_USER_APP_DIR}" LVGL_AI_USER_APP_DIR)

# PNG evidence is written with libpng + zlib, not LVGL's bundled lodepng.
# tools/fetch_png.py installs the pinned sources under third_party/.
if(NOT DEFINED LVGL_AI_ZLIB_SRC OR LVGL_AI_ZLIB_SRC STREQUAL "")
    message(FATAL_ERROR "LVGL_AI_ZLIB_SRC is required; run: python -I core/tools/fetch_png.py --repo-root .")
endif()
if(NOT DEFINED LVGL_AI_LIBPNG_SRC OR LVGL_AI_LIBPNG_SRC STREQUAL "")
    message(FATAL_ERROR "LVGL_AI_LIBPNG_SRC is required; run: python -I core/tools/fetch_png.py --repo-root .")
endif()
file(TO_CMAKE_PATH "${LVGL_AI_ZLIB_SRC}" LVGL_AI_ZLIB_SRC)
file(TO_CMAKE_PATH "${LVGL_AI_LIBPNG_SRC}" LVGL_AI_LIBPNG_SRC)
if(NOT EXISTS "${LVGL_AI_ZLIB_SRC}/zlib.h")
    message(FATAL_ERROR "zlib source not found at ${LVGL_AI_ZLIB_SRC}; run: python -I core/tools/fetch_png.py --repo-root .")
endif()
if(NOT EXISTS "${LVGL_AI_LIBPNG_SRC}/png.h"
   OR NOT EXISTS "${LVGL_AI_LIBPNG_SRC}/scripts/pnglibconf.h.prebuilt")
    message(FATAL_ERROR "libpng source not found at ${LVGL_AI_LIBPNG_SRC}; run: python -I core/tools/fetch_png.py --repo-root .")
endif()

message(STATUS "lvgl_engine: LVGL ${LVGL_AI_LVGL_VERSION} from ${LVGL_AI_LVGL_SRC}")
message(STATUS "lvgl_engine: zlib from ${LVGL_AI_ZLIB_SRC}")
message(STATUS "lvgl_engine: libpng from ${LVGL_AI_LIBPNG_SRC}")

# Host SDK export maps the build tree to a relative prefix so __FILE__ and
# debug information never embed the build machine's absolute paths.
if(DEFINED LVGL_AI_FILE_PREFIX_MAP AND NOT LVGL_AI_FILE_PREFIX_MAP STREQUAL "")
    file(TO_CMAKE_PATH "${LVGL_AI_FILE_PREFIX_MAP}" LVGL_AI_FILE_PREFIX_MAP)
    add_compile_options("SHELL:-ffile-prefix-map=${LVGL_AI_FILE_PREFIX_MAP}=.")
endif()
if(DEFINED LVGL_AI_LVGL_SRC_PREFIX_MAP
   AND NOT LVGL_AI_LVGL_SRC_PREFIX_MAP STREQUAL "")
    file(TO_CMAKE_PATH "${LVGL_AI_LVGL_SRC_PREFIX_MAP}" LVGL_AI_LVGL_SRC_PREFIX_MAP)
    add_compile_options("SHELL:-ffile-prefix-map=${LVGL_AI_LVGL_SRC_PREFIX_MAP}=lvgl-src/${LVGL_AI_LVGL_VERSION}")
endif()

# Version family: the adapter is the only engine-owned target allowed to
# include LVGL headers (user/app is user code), and the lodepng copy moves
# between the 8.x and 9.x trees.
if(LVGL_AI_LVGL_VERSION MATCHES "^9\\.")
    set(LVGL_AI_LVGL_MAJOR 9)
    set(LVGL_AI_ADAPTER_SOURCE adapter_9x.c)
    set(LVGL_AI_LODEPNG_DIR "${LVGL_AI_LVGL_SRC}/src/libs/lodepng")
elseif(LVGL_AI_LVGL_VERSION MATCHES "^8\\.")
    set(LVGL_AI_LVGL_MAJOR 8)
    set(LVGL_AI_ADAPTER_SOURCE adapter_8x.c)
    set(LVGL_AI_LODEPNG_DIR "${LVGL_AI_LVGL_SRC}/src/extra/libs/png")
else()
    message(FATAL_ERROR
        "no adapter for LVGL ${LVGL_AI_LVGL_VERSION}; supported families are 8.x and 9.x")
endif()

# User code may live directly in user/app or in per-app subdirectories such as
# user/app/<app>/; every *.c in the tree belongs to the one app target.
file(GLOB_RECURSE LVGL_AI_USER_SOURCES CONFIGURE_DEPENDS "${LVGL_AI_USER_APP_DIR}/*.c")
if(NOT LVGL_AI_USER_SOURCES)
    message(FATAL_ERROR "no C sources found in ${LVGL_AI_USER_APP_DIR}")
endif()

get_filename_component(LVGL_AI_USER_DIR "${LVGL_AI_USER_APP_DIR}" DIRECTORY)

# The tool owns lv_conf.h; users only write user/app.
# 9.4/9.5 read LV_BUILD_CONF_DIR via os_desktop.cmake; 9.6 uses main.cmake
# with the same variables. 9.1 and 8.x read LV_CONF_PATH. The
# LVGL_MAJOR_8 define selects the 8.x block inside lv_conf.h before any
# LVGL source is compiled.
if(LVGL_AI_LVGL_MAJOR EQUAL 8)
    set(LV_CONF_PATH "${CMAKE_CURRENT_SOURCE_DIR}/lv_conf.h" CACHE FILEPATH "" FORCE)
    add_compile_definitions(LVGL_MAJOR_8=1)
elseif(EXISTS "${LVGL_AI_LVGL_SRC}/env_support/cmake/os_desktop.cmake"
       OR EXISTS "${LVGL_AI_LVGL_SRC}/env_support/cmake/main.cmake")
    set(LV_BUILD_CONF_DIR "${CMAKE_CURRENT_SOURCE_DIR}" CACHE PATH "" FORCE)
    set(CONFIG_LV_USE_THORVG OFF CACHE BOOL "" FORCE)
    set(CONFIG_LV_USE_THORVG_INTERNAL OFF CACHE BOOL "" FORCE)
    set(CONFIG_LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)
    set(CONFIG_LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(LV_BUILD_INSTALL OFF CACHE BOOL "" FORCE)
else()
    set(LV_CONF_PATH "${CMAKE_CURRENT_SOURCE_DIR}/lv_conf.h" CACHE FILEPATH "" FORCE)
    set(LV_CONF_BUILD_DISABLE_THORVG_INTERNAL ON CACHE BOOL "" FORCE)
    set(LV_CONF_BUILD_DISABLE_EXAMPLES ON CACHE BOOL "" FORCE)
    set(LV_CONF_BUILD_DISABLE_DEMOS ON CACHE BOOL "" FORCE)
endif()

add_subdirectory(${LVGL_AI_LVGL_SRC} ${CMAKE_CURRENT_BINARY_DIR}/lvgl)

# Third-party PNG encoder, built statically from the fetched sources.
add_library(lvgl_ai_zlib STATIC
    ${LVGL_AI_ZLIB_SRC}/adler32.c
    ${LVGL_AI_ZLIB_SRC}/compress.c
    ${LVGL_AI_ZLIB_SRC}/crc32.c
    ${LVGL_AI_ZLIB_SRC}/deflate.c
    ${LVGL_AI_ZLIB_SRC}/infback.c
    ${LVGL_AI_ZLIB_SRC}/inffast.c
    ${LVGL_AI_ZLIB_SRC}/inflate.c
    ${LVGL_AI_ZLIB_SRC}/inftrees.c
    ${LVGL_AI_ZLIB_SRC}/trees.c
    ${LVGL_AI_ZLIB_SRC}/uncompr.c
    ${LVGL_AI_ZLIB_SRC}/zutil.c
)
target_include_directories(lvgl_ai_zlib PUBLIC ${LVGL_AI_ZLIB_SRC})
target_compile_options(lvgl_ai_zlib PRIVATE -w)

# png.h includes "pnglibconf.h"; use the prebuilt configuration instead of
# libpng's full configure step.
set(LVGL_AI_PNGCONF_DIR "${CMAKE_CURRENT_BINARY_DIR}/pnglibconf")
file(MAKE_DIRECTORY "${LVGL_AI_PNGCONF_DIR}")
configure_file(
    "${LVGL_AI_LIBPNG_SRC}/scripts/pnglibconf.h.prebuilt"
    "${LVGL_AI_PNGCONF_DIR}/pnglibconf.h"
    COPYONLY
)
add_library(lvgl_ai_libpng STATIC
    ${LVGL_AI_LIBPNG_SRC}/png.c
    ${LVGL_AI_LIBPNG_SRC}/pngerror.c
    ${LVGL_AI_LIBPNG_SRC}/pngget.c
    ${LVGL_AI_LIBPNG_SRC}/pngmem.c
    ${LVGL_AI_LIBPNG_SRC}/pngpread.c
    ${LVGL_AI_LIBPNG_SRC}/pngread.c
    ${LVGL_AI_LIBPNG_SRC}/pngrio.c
    ${LVGL_AI_LIBPNG_SRC}/pngrtran.c
    ${LVGL_AI_LIBPNG_SRC}/pngrutil.c
    ${LVGL_AI_LIBPNG_SRC}/pngset.c
    ${LVGL_AI_LIBPNG_SRC}/pngtrans.c
    ${LVGL_AI_LIBPNG_SRC}/pngwio.c
    ${LVGL_AI_LIBPNG_SRC}/pngwrite.c
    ${LVGL_AI_LIBPNG_SRC}/pngwtran.c
    ${LVGL_AI_LIBPNG_SRC}/pngwutil.c
)
target_include_directories(lvgl_ai_libpng PUBLIC
    ${LVGL_AI_PNGCONF_DIR}
    ${LVGL_AI_LIBPNG_SRC}
    ${LVGL_AI_ZLIB_SRC}
)
target_compile_definitions(lvgl_ai_libpng PRIVATE
    PNG_ARM_NEON_OPT=0
    PNG_INTEL_SSE_OPT=0
)
target_link_libraries(lvgl_ai_libpng PUBLIC lvgl_ai_zlib)
target_compile_options(lvgl_ai_libpng PRIVATE -w)

# Adapter target: adapter_common.c holds the version-independent mechanics;
# the version-specific source is the only engine source that includes LVGL
# and lodepng headers.
#
# A host SDK build overrides LVGL_AI_LVGL_SRC_LABEL with a portable label such
# as "prebuilt-9.6", so the library never embeds the build machine's paths.
if(NOT DEFINED LVGL_AI_LVGL_SRC_LABEL OR LVGL_AI_LVGL_SRC_LABEL STREQUAL "")
    set(LVGL_AI_LVGL_SRC_LABEL "${LVGL_AI_LVGL_SRC}")
endif()
file(TO_CMAKE_PATH "${LVGL_AI_LVGL_SRC_LABEL}" LVGL_AI_LVGL_SRC_LABEL)
add_library(adapter STATIC adapter_common.c ${LVGL_AI_ADAPTER_SOURCE})
target_link_libraries(adapter PRIVATE lvgl)
target_include_directories(adapter PRIVATE
    ${LVGL_AI_LODEPNG_DIR}
)
# The engine reports the exact source tree it was built from. The label is
# already normalized to forward slashes above, so it is safe inside a C string.
target_compile_definitions(adapter PRIVATE
    "LVGL_SRC_PATH=\"${LVGL_AI_LVGL_SRC_LABEL}\""
)
target_compile_options(adapter PRIVATE -Wall -Wextra)

# User code is compiled automatically from user/app/**/*.c and keeps LVGL
# headers.
add_library(user_app STATIC ${LVGL_AI_USER_SOURCES})
target_link_libraries(user_app PRIVATE lvgl)
target_include_directories(user_app PRIVATE
    ${LVGL_AI_USER_DIR}
    ${LVGL_AI_USER_APP_DIR}
)
target_compile_options(user_app PRIVATE -Wall -Wextra)

# Engine sources only see adapter.h, never version LVGL headers. The OBJECT
# library is the single compilation of these sources: the executable links the
# objects directly and the SDK export archives the same objects into
# libengine.a.
add_library(engine_core OBJECT
    protocol.c
    session.c
    capture.c
    frame_encoder.c
    timeline.c
    frame_analysis.c
    frame_diff.c
    json.c
    png_writer.c
    window.c
    stdin_queue.c
)
target_include_directories(engine_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(engine_core PRIVATE lvgl_ai_libpng)
target_compile_options(engine_core PRIVATE -Wall -Wextra)

add_executable(lvgl_engine main.c)
target_link_libraries(lvgl_engine PRIVATE engine_core adapter user_app lvgl_ai_libpng)
if(NOT WIN32)
    find_package(Threads REQUIRED)
    target_link_libraries(lvgl_engine PRIVATE Threads::Threads)
endif()
target_include_directories(lvgl_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_options(lvgl_engine PRIVATE -Wall -Wextra)
# window.c is a stub on other platforms; only Win32 needs GDI/user32.
if(WIN32)
    target_link_libraries(lvgl_engine PRIVATE gdi32 user32)
endif()

set_target_properties(lvgl_engine PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)

# Host SDK export: a static archive over the same engine objects, plus a
# convenience target that builds every library the SDK manifest lists.
add_library(engine_archive STATIC $<TARGET_OBJECTS:engine_core>)
set_target_properties(engine_archive PROPERTIES OUTPUT_NAME engine)
add_custom_target(lvgl_ai_sdk
    DEPENDS lvgl adapter engine_archive lvgl_ai_libpng lvgl_ai_zlib
)

# SDK builds collect all archives into one directory; normal builds leave the
# default CMake layout untouched.
if(DEFINED LVGL_AI_SDK_LIBS_DIR AND NOT LVGL_AI_SDK_LIBS_DIR STREQUAL "")
    file(TO_CMAKE_PATH "${LVGL_AI_SDK_LIBS_DIR}" LVGL_AI_SDK_LIBS_DIR)
    set_target_properties(lvgl_ai_zlib lvgl_ai_libpng adapter engine_archive
        PROPERTIES ARCHIVE_OUTPUT_DIRECTORY "${LVGL_AI_SDK_LIBS_DIR}")
    set_target_properties(lvgl PROPERTIES
        ARCHIVE_OUTPUT_DIRECTORY "${LVGL_AI_SDK_LIBS_DIR}")
endif()
