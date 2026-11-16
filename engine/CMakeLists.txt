cmake_minimum_required(VERSION 3.20)
project(lvgl_engine C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(NOT DEFINED LVGL_VERIFY_LOOP_LVGL_SRC OR LVGL_VERIFY_LOOP_LVGL_SRC STREQUAL "")
    message(FATAL_ERROR "LVGL_VERIFY_LOOP_LVGL_SRC is required")
endif()

# The Python layer passes native Windows paths. Normalize them before GLOB:
# CONFIGURE_DEPENDS writes the pattern into VerifyGlobs.cmake, where
# backslashes are parsed as escape sequences.
file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_LVGL_SRC}" LVGL_VERIFY_LOOP_LVGL_SRC)

# LVGL 9.6 keeps public headers in include/lvgl; 9.1-9.5 keep lvgl.h at the
# source root. Accept both layouts; the lvgl target exports the right includes.
if(NOT EXISTS "${LVGL_VERIFY_LOOP_LVGL_SRC}/include/lvgl/lvgl.h"
   AND NOT EXISTS "${LVGL_VERIFY_LOOP_LVGL_SRC}/lvgl.h")
    message(FATAL_ERROR "LVGL source not found at ${LVGL_VERIFY_LOOP_LVGL_SRC}")
endif()

if(NOT DEFINED LVGL_VERIFY_LOOP_APPS_DIR OR NOT EXISTS "${LVGL_VERIFY_LOOP_APPS_DIR}")
    message(FATAL_ERROR "apps directory not found: ${LVGL_VERIFY_LOOP_APPS_DIR}")
endif()
file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_APPS_DIR}" LVGL_VERIFY_LOOP_APPS_DIR)

# PNG evidence is written with libpng + zlib, not LVGL's bundled lodepng.
# scripts/fetch_png.py installs the pinned sources under engine/third_party/.
if(NOT DEFINED LVGL_VERIFY_LOOP_ZLIB_SRC OR LVGL_VERIFY_LOOP_ZLIB_SRC STREQUAL "")
    message(FATAL_ERROR "LVGL_VERIFY_LOOP_ZLIB_SRC is required; run: python -I scripts/fetch_png.py --repo-root .")
endif()
if(NOT DEFINED LVGL_VERIFY_LOOP_LIBPNG_SRC OR LVGL_VERIFY_LOOP_LIBPNG_SRC STREQUAL "")
    message(FATAL_ERROR "LVGL_VERIFY_LOOP_LIBPNG_SRC is required; run: python -I scripts/fetch_png.py --repo-root .")
endif()
file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_ZLIB_SRC}" LVGL_VERIFY_LOOP_ZLIB_SRC)
file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_LIBPNG_SRC}" LVGL_VERIFY_LOOP_LIBPNG_SRC)
if(NOT EXISTS "${LVGL_VERIFY_LOOP_ZLIB_SRC}/zlib.h")
    message(FATAL_ERROR "zlib source not found at ${LVGL_VERIFY_LOOP_ZLIB_SRC}; run: python -I scripts/fetch_png.py --repo-root .")
endif()
if(NOT EXISTS "${LVGL_VERIFY_LOOP_LIBPNG_SRC}/png.h"
   OR NOT EXISTS "${LVGL_VERIFY_LOOP_LIBPNG_SRC}/scripts/pnglibconf.h.prebuilt")
    message(FATAL_ERROR "libpng source not found at ${LVGL_VERIFY_LOOP_LIBPNG_SRC}; run: python -I scripts/fetch_png.py --repo-root .")
endif()

# LV_USE_FREETYPE is on in engine/adapter/lv_conf.h. Windows uses the vendored
# FreeType 2.13.2 headers and MinGW import library; the DLL is the same one
# the asset converter ships, and is copied next to lvgl_engine.exe because
# Windows resolves it from the executable directory.
if(WIN32)
    set(LVGL_VERIFY_LOOP_FREETYPE_INCLUDE_DIR
        "${CMAKE_CURRENT_SOURCE_DIR}/third_party/freetype/include" CACHE PATH
        "FreeType headers for the host engine")
    set(LVGL_VERIFY_LOOP_FREETYPE_LIBRARY
        "${CMAKE_CURRENT_SOURCE_DIR}/third_party/freetype/lib/libfreetype.dll.a" CACHE FILEPATH
        "FreeType import library for the host engine")
    if(NOT DEFINED LVGL_VERIFY_LOOP_FREETYPE_DLL OR LVGL_VERIFY_LOOP_FREETYPE_DLL STREQUAL "")
        set(LVGL_VERIFY_LOOP_FREETYPE_DLL
            "${CMAKE_CURRENT_SOURCE_DIR}/../console/assets/vendor/freetype/libfreetype.dll"
            CACHE FILEPATH "FreeType runtime DLL")
    endif()
    file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_FREETYPE_DLL}" LVGL_VERIFY_LOOP_FREETYPE_DLL)
    if(NOT EXISTS "${LVGL_VERIFY_LOOP_FREETYPE_INCLUDE_DIR}/ft2build.h")
        message(FATAL_ERROR "FreeType headers not found at ${LVGL_VERIFY_LOOP_FREETYPE_INCLUDE_DIR}")
    endif()
    if(NOT EXISTS "${LVGL_VERIFY_LOOP_FREETYPE_LIBRARY}")
        message(FATAL_ERROR "FreeType import library not found at ${LVGL_VERIFY_LOOP_FREETYPE_LIBRARY}")
    endif()
    if(NOT EXISTS "${LVGL_VERIFY_LOOP_FREETYPE_DLL}")
        message(FATAL_ERROR "FreeType runtime DLL not found at ${LVGL_VERIFY_LOOP_FREETYPE_DLL}")
    endif()
endif()

message(STATUS "lvgl_engine: LVGL ${LVGL_VERIFY_LOOP_LVGL_VERSION} from ${LVGL_VERIFY_LOOP_LVGL_SRC}")
message(STATUS "lvgl_engine: zlib from ${LVGL_VERIFY_LOOP_ZLIB_SRC}")
message(STATUS "lvgl_engine: libpng from ${LVGL_VERIFY_LOOP_LIBPNG_SRC}")
if(WIN32)
    message(STATUS "lvgl_engine: FreeType from ${LVGL_VERIFY_LOOP_FREETYPE_LIBRARY}")
endif()

# Host SDK export maps the build tree to a relative prefix so __FILE__ and
# debug information never embed the build machine's absolute paths.
if(DEFINED LVGL_VERIFY_LOOP_FILE_PREFIX_MAP AND NOT LVGL_VERIFY_LOOP_FILE_PREFIX_MAP STREQUAL "")
    file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_FILE_PREFIX_MAP}" LVGL_VERIFY_LOOP_FILE_PREFIX_MAP)
    add_compile_options("SHELL:-ffile-prefix-map=${LVGL_VERIFY_LOOP_FILE_PREFIX_MAP}=.")
endif()
if(DEFINED LVGL_VERIFY_LOOP_LVGL_SRC_PREFIX_MAP
   AND NOT LVGL_VERIFY_LOOP_LVGL_SRC_PREFIX_MAP STREQUAL "")
    file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_LVGL_SRC_PREFIX_MAP}" LVGL_VERIFY_LOOP_LVGL_SRC_PREFIX_MAP)
    add_compile_options("SHELL:-ffile-prefix-map=${LVGL_VERIFY_LOOP_LVGL_SRC_PREFIX_MAP}=engine/lvgl/${LVGL_VERIFY_LOOP_LVGL_VERSION}")
endif()

# Version family: the adapter is the only engine-owned target allowed to
# include LVGL headers (apps is user code), and the lodepng copy moves
# between the 8.x and 9.x trees.
if(LVGL_VERIFY_LOOP_LVGL_VERSION MATCHES "^9\\.")
    set(LVGL_VERIFY_LOOP_LVGL_MAJOR 9)
    set(LVGL_VERIFY_LOOP_ADAPTER_SOURCE adapter/adapter_9x.c)
    set(LVGL_VERIFY_LOOP_LODEPNG_DIR "${LVGL_VERIFY_LOOP_LVGL_SRC}/src/libs/lodepng")
elseif(LVGL_VERIFY_LOOP_LVGL_VERSION MATCHES "^8\\.")
    set(LVGL_VERIFY_LOOP_LVGL_MAJOR 8)
    set(LVGL_VERIFY_LOOP_ADAPTER_SOURCE adapter/adapter_8x.c)
    set(LVGL_VERIFY_LOOP_LODEPNG_DIR "${LVGL_VERIFY_LOOP_LVGL_SRC}/src/extra/libs/png")
else()
    message(FATAL_ERROR
        "no adapter for LVGL ${LVGL_VERIFY_LOOP_LVGL_VERSION}; supported families are 8.x and 9.x")
endif()

# User code may live directly in apps or in per-app subdirectories such as
# user/app/<app>/; every *.c in the tree belongs to the one app target.
file(GLOB_RECURSE LVGL_VERIFY_LOOP_USER_SOURCES CONFIGURE_DEPENDS "${LVGL_VERIFY_LOOP_APPS_DIR}/*.c")
if(NOT LVGL_VERIFY_LOOP_USER_SOURCES)
    message(FATAL_ERROR "no C sources found in ${LVGL_VERIFY_LOOP_APPS_DIR}")
endif()

get_filename_component(LVGL_VERIFY_LOOP_USER_DIR "${LVGL_VERIFY_LOOP_APPS_DIR}" DIRECTORY)

# The tool owns lv_conf.h (engine/adapter); users only write apps.
# 9.4/9.5 read LV_BUILD_CONF_DIR via os_desktop.cmake; 9.6 uses main.cmake
# with the same variables. 9.1 and 8.x read LV_CONF_PATH. The
# LVGL_MAJOR_8 define selects the 8.x block inside lv_conf.h before any
# LVGL source is compiled.
if(LVGL_VERIFY_LOOP_LVGL_MAJOR EQUAL 8)
    set(LV_CONF_PATH "${CMAKE_CURRENT_SOURCE_DIR}/adapter/lv_conf.h" CACHE FILEPATH "" FORCE)
    add_compile_definitions(LVGL_MAJOR_8=1)
elseif(EXISTS "${LVGL_VERIFY_LOOP_LVGL_SRC}/env_support/cmake/os_desktop.cmake"
       OR EXISTS "${LVGL_VERIFY_LOOP_LVGL_SRC}/env_support/cmake/main.cmake")
    set(LV_BUILD_CONF_DIR "${CMAKE_CURRENT_SOURCE_DIR}/adapter" CACHE PATH "" FORCE)
    set(CONFIG_LV_USE_THORVG OFF CACHE BOOL "" FORCE)
    set(CONFIG_LV_USE_THORVG_INTERNAL OFF CACHE BOOL "" FORCE)
    set(CONFIG_LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)
    set(CONFIG_LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(LV_BUILD_INSTALL OFF CACHE BOOL "" FORCE)
else()
    set(LV_CONF_PATH "${CMAKE_CURRENT_SOURCE_DIR}/adapter/lv_conf.h" CACHE FILEPATH "" FORCE)
    set(LV_CONF_BUILD_DISABLE_THORVG_INTERNAL ON CACHE BOOL "" FORCE)
    set(LV_CONF_BUILD_DISABLE_EXAMPLES ON CACHE BOOL "" FORCE)
    set(LV_CONF_BUILD_DISABLE_DEMOS ON CACHE BOOL "" FORCE)
endif()

add_subdirectory(${LVGL_VERIFY_LOOP_LVGL_SRC} ${CMAKE_CURRENT_BINARY_DIR}/lvgl)

# LVGL's FreeType module (enabled by lv_conf.h) compiles against the vendored
# headers and needs the import library when the engine is linked.
if(WIN32)
    target_include_directories(lvgl PRIVATE "${LVGL_VERIFY_LOOP_FREETYPE_INCLUDE_DIR}")
    target_link_libraries(lvgl PUBLIC "${LVGL_VERIFY_LOOP_FREETYPE_LIBRARY}")
else()
    find_package(Freetype REQUIRED)
    target_link_libraries(lvgl PUBLIC Freetype::Freetype)
endif()

# Third-party PNG encoder, built statically from the fetched sources.
add_library(lvgl_verify_loop_zlib STATIC
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/adler32.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/compress.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/crc32.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/deflate.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/infback.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/inffast.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/inflate.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/inftrees.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/trees.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/uncompr.c
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}/zutil.c
)
target_include_directories(lvgl_verify_loop_zlib PUBLIC ${LVGL_VERIFY_LOOP_ZLIB_SRC})
target_compile_options(lvgl_verify_loop_zlib PRIVATE -w)

# png.h includes "pnglibconf.h"; use the prebuilt configuration instead of
# libpng's full configure step.
set(LVGL_VERIFY_LOOP_PNGCONF_DIR "${CMAKE_CURRENT_BINARY_DIR}/pnglibconf")
file(MAKE_DIRECTORY "${LVGL_VERIFY_LOOP_PNGCONF_DIR}")
configure_file(
    "${LVGL_VERIFY_LOOP_LIBPNG_SRC}/scripts/pnglibconf.h.prebuilt"
    "${LVGL_VERIFY_LOOP_PNGCONF_DIR}/pnglibconf.h"
    COPYONLY
)
add_library(lvgl_verify_loop_libpng STATIC
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/png.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngerror.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngget.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngmem.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngpread.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngread.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngrio.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngrtran.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngrutil.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngset.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngtrans.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngwio.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngwrite.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngwtran.c
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}/pngwutil.c
)
target_include_directories(lvgl_verify_loop_libpng PUBLIC
    ${LVGL_VERIFY_LOOP_PNGCONF_DIR}
    ${LVGL_VERIFY_LOOP_LIBPNG_SRC}
    ${LVGL_VERIFY_LOOP_ZLIB_SRC}
)
target_compile_definitions(lvgl_verify_loop_libpng PRIVATE
    PNG_ARM_NEON_OPT=0
    PNG_INTEL_SSE_OPT=0
)
target_link_libraries(lvgl_verify_loop_libpng PUBLIC lvgl_verify_loop_zlib)
target_compile_options(lvgl_verify_loop_libpng PRIVATE -w)

# Adapter target: adapter_common.c holds the version-independent mechanics;
# the version-specific source is the only engine source that includes LVGL
# and lodepng headers.
#
# A host SDK build overrides LVGL_VERIFY_LOOP_LVGL_SRC_LABEL with a portable label such
# as "prebuilt-9.6", so the library never embeds the build machine's paths.
if(NOT DEFINED LVGL_VERIFY_LOOP_LVGL_SRC_LABEL OR LVGL_VERIFY_LOOP_LVGL_SRC_LABEL STREQUAL "")
    set(LVGL_VERIFY_LOOP_LVGL_SRC_LABEL "${LVGL_VERIFY_LOOP_LVGL_SRC}")
endif()
file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_LVGL_SRC_LABEL}" LVGL_VERIFY_LOOP_LVGL_SRC_LABEL)
add_library(adapter STATIC
    adapter/adapter_common.c
    ${LVGL_VERIFY_LOOP_ADAPTER_SOURCE}
)
target_link_libraries(adapter PRIVATE lvgl)
target_include_directories(adapter PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/adapter
    ${CMAKE_CURRENT_SOURCE_DIR}/render
    ${LVGL_VERIFY_LOOP_LODEPNG_DIR}
)
# The engine reports the exact source tree it was built from. The label is
# already normalized to forward slashes above, so it is safe inside a C string.
target_compile_definitions(adapter PRIVATE
    "LVGL_SRC_PATH=\"${LVGL_VERIFY_LOOP_LVGL_SRC_LABEL}\""
)
target_compile_options(adapter PRIVATE -Wall -Wextra)

# User code is compiled automatically from user/app/**/*.c and keeps LVGL
# headers.
add_library(user_app STATIC ${LVGL_VERIFY_LOOP_USER_SOURCES})
target_link_libraries(user_app PRIVATE lvgl)
target_include_directories(user_app PRIVATE
    ${LVGL_VERIFY_LOOP_USER_DIR}
    ${LVGL_VERIFY_LOOP_APPS_DIR}
)
if(WIN32)
    target_include_directories(user_app PRIVATE "${LVGL_VERIFY_LOOP_FREETYPE_INCLUDE_DIR}")
endif()
target_compile_options(user_app PRIVATE -Wall -Wextra)

# Engine sources only see adapter.h, never version LVGL headers. The OBJECT
# library is the single compilation of these sources: the executable links the
# objects directly and the SDK export archives the same objects into
# libengine.a.
add_library(engine_core OBJECT
    core/protocol.c
    core/session.c
    render/capture.c
    render/frame_encoder.c
    core/timeline.c
    render/frame_analysis.c
    render/frame_diff.c
    render/json.c
    render/png_writer.c
    core/window.c
    core/stdin_queue.c
)
target_include_directories(engine_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/core
    ${CMAKE_CURRENT_SOURCE_DIR}/render
    ${CMAKE_CURRENT_SOURCE_DIR}/adapter
)
target_link_libraries(engine_core PRIVATE lvgl_verify_loop_libpng)
target_compile_options(engine_core PRIVATE -Wall -Wextra)

add_executable(lvgl_engine core/main.c)
target_link_libraries(lvgl_engine PRIVATE engine_core adapter user_app lvgl_verify_loop_libpng)
if(NOT WIN32)
    find_package(Threads REQUIRED)
    target_link_libraries(lvgl_engine PRIVATE Threads::Threads)
endif()
target_include_directories(lvgl_engine PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/core
    ${CMAKE_CURRENT_SOURCE_DIR}/render
    ${CMAKE_CURRENT_SOURCE_DIR}/adapter
)
target_compile_options(lvgl_engine PRIVATE -Wall -Wextra)
# window.c is a stub on other platforms; only Win32 needs GDI/user32.
if(WIN32)
    target_link_libraries(lvgl_engine PRIVATE gdi32 user32)
endif()

set_target_properties(lvgl_engine PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)

if(WIN32)
    add_custom_command(TARGET lvgl_engine POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${LVGL_VERIFY_LOOP_FREETYPE_DLL}"
            "$<TARGET_FILE_DIR:lvgl_engine>/libfreetype.dll"
        COMMENT "Copying libfreetype.dll next to lvgl_engine.exe"
        VERBATIM
    )
endif()

# Host SDK export: a static archive over the same engine objects, plus a
# convenience target that builds every library the SDK manifest lists.
add_library(engine_archive STATIC $<TARGET_OBJECTS:engine_core>)
set_target_properties(engine_archive PROPERTIES OUTPUT_NAME engine)
add_custom_target(lvgl_verify_loop_sdk
    DEPENDS lvgl adapter engine_archive lvgl_verify_loop_libpng lvgl_verify_loop_zlib
)

# SDK builds collect all archives into one directory; normal builds leave the
# default CMake layout untouched.
if(DEFINED LVGL_VERIFY_LOOP_SDK_LIBS_DIR AND NOT LVGL_VERIFY_LOOP_SDK_LIBS_DIR STREQUAL "")
    file(TO_CMAKE_PATH "${LVGL_VERIFY_LOOP_SDK_LIBS_DIR}" LVGL_VERIFY_LOOP_SDK_LIBS_DIR)
    set_target_properties(lvgl_verify_loop_zlib lvgl_verify_loop_libpng adapter engine_archive
        PROPERTIES ARCHIVE_OUTPUT_DIRECTORY "${LVGL_VERIFY_LOOP_SDK_LIBS_DIR}")
    set_target_properties(lvgl PROPERTIES
        ARCHIVE_OUTPUT_DIRECTORY "${LVGL_VERIFY_LOOP_SDK_LIBS_DIR}")
endif()
