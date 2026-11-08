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

message(STATUS "lvgl_engine: LVGL ${LVGL_AI_LVGL_VERSION} from ${LVGL_AI_LVGL_SRC}")

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
set(LVGL_AI_USER_ASSET_DIR "${LVGL_AI_USER_DIR}/asset" CACHE PATH "Directory with user asset headers or C arrays")

# The tool owns lv_conf.h; users only write user/app and user/asset.
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

# Adapter target: adapter_common.c holds the version-independent mechanics;
# the version-specific source is the only engine source that includes LVGL
# and lodepng headers.
add_library(adapter STATIC adapter_common.c ${LVGL_AI_ADAPTER_SOURCE})
target_link_libraries(adapter PRIVATE lvgl)
target_include_directories(adapter PRIVATE
    ${LVGL_AI_LODEPNG_DIR}
)
# The engine reports the exact source tree it was built from. LVGL_AI_LVGL_SRC is
# already normalized to forward slashes above, so it is safe inside a C string.
target_compile_definitions(adapter PRIVATE
    "LVGL_SRC_PATH=\"${LVGL_AI_LVGL_SRC}\""
)
target_compile_options(adapter PRIVATE -Wall -Wextra)

# User code is compiled automatically from user/app/**/*.c and keeps LVGL
# headers.
add_library(user_app STATIC ${LVGL_AI_USER_SOURCES})
target_link_libraries(user_app PRIVATE lvgl)
target_include_directories(user_app PRIVATE
    ${LVGL_AI_USER_DIR}
    ${LVGL_AI_USER_APP_DIR}
    ${LVGL_AI_USER_ASSET_DIR}
)
target_compile_options(user_app PRIVATE -Wall -Wextra)

# Engine sources only see adapter.h, never version LVGL headers.
add_executable(lvgl_engine
    main.c
    protocol.c
    session.c
    capture.c
    timeline.c
    frame_analysis.c
    frame_diff.c
    json.c
    window.c
    stdin_queue.c
)
target_link_libraries(lvgl_engine PRIVATE adapter user_app)
target_include_directories(lvgl_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_options(lvgl_engine PRIVATE -Wall -Wextra)
# window.c is a stub on other platforms; only Win32 needs GDI/user32.
if(WIN32)
    target_link_libraries(lvgl_engine PRIVATE gdi32 user32)
endif()

set_target_properties(lvgl_engine PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)
