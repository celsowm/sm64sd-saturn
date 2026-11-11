cmake_minimum_required(VERSION 3.24)
project(sm64ds_saturn LANGUAGES C)

# Keep ROM-derived C/H outside the source tree and therefore outside Git.
if(NOT DEFINED SM64DS_GENERATED_DIR OR NOT EXISTS "${SM64DS_GENERATED_DIR}/mario_preview.c")
  message(FATAL_ERROR "Set -DSM64DS_GENERATED_DIR=/private/derived to your locally generated mario_preview.c/.h")
endif()

find_package(LibSaturn 0.1 CONFIG REQUIRED)
option(SM64DS_ENABLE_SKYBOX "Render camera-following skybox alongside Mario" OFF)
set(viewer_sources
  src/viewer.c
  runtime/sm64ds_pose.c
  runtime/sm64ds_background.c
  "${SM64DS_GENERATED_DIR}/mario_preview.c")
if(SM64DS_ENABLE_SKYBOX)
  if(NOT EXISTS "${SM64DS_GENERATED_DIR}/skybox_preview.c" OR
     NOT EXISTS "${SM64DS_GENERATED_DIR}/skybox_preview.h")
    message(FATAL_ERROR "SM64DS_ENABLE_SKYBOX requires locally generated skybox_preview.c/.h")
  endif()
  list(APPEND viewer_sources "${SM64DS_GENERATED_DIR}/skybox_preview.c")
endif()
add_executable(sm64ds_viewer ${viewer_sources})
target_compile_definitions(sm64ds_viewer PRIVATE
  SM64DS_ENABLE_SKYBOX=$<BOOL:${SM64DS_ENABLE_SKYBOX}>)
target_include_directories(sm64ds_viewer PRIVATE
  "${CMAKE_SOURCE_DIR}/runtime"
  "${SM64DS_GENERATED_DIR}")
target_link_libraries(sm64ds_viewer PRIVATE LibSaturn::Saturn)
libsaturn_configure_executable(sm64ds_viewer)
libsaturn_add_binary(sm64ds_viewer)
libsaturn_add_disc(sm64ds_viewer NAME sm64ds_viewer)

option(SM64DS_BUILD_CASTLE "Build the playable castle exterior" OFF)
if(SM64DS_BUILD_CASTLE)
  if(NOT EXISTS "${SM64DS_GENERATED_DIR}/castle_scene.c")
    message(FATAL_ERROR "Run tools/prepare_castle.py into SM64DS_GENERATED_DIR first")
  endif()
  add_executable(sm64ds_castle src/castle.c runtime/sm64ds_play.c
    runtime/sm64ds_pose.c runtime/sm64ds_background.c
    "${SM64DS_GENERATED_DIR}/mario_preview.c"
    "${SM64DS_GENERATED_DIR}/castle_scene.c"
    "${SM64DS_GENERATED_DIR}/mario_head.c"
    "${SM64DS_GENERATED_DIR}/skybox_preview.c")
  target_include_directories(sm64ds_castle PRIVATE runtime "${SM64DS_GENERATED_DIR}")
  target_link_libraries(sm64ds_castle PRIVATE LibSaturn::Saturn)
  libsaturn_configure_executable(sm64ds_castle)
  libsaturn_add_binary(sm64ds_castle)
  libsaturn_add_disc(sm64ds_castle NAME sm64ds_castle)
endif()
