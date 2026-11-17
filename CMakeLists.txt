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

option(SM64DS_BUILD_SPRITE_FIXTURE "Build the ROM-free triangle UV fixture" OFF)
if(SM64DS_BUILD_SPRITE_FIXTURE)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  set(fixture_header "${CMAKE_CURRENT_BINARY_DIR}/sprite_fixture_data.h")
  add_custom_command(OUTPUT "${fixture_header}"
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tools/make_sprite_fixture.py" --out "${fixture_header}"
    DEPENDS tools/make_sprite_fixture.py tools/sm64ds_pipeline/textures.py tools/sm64ds_pipeline/common.py
    VERBATIM)
  add_executable(sm64ds_sprite_fixture src/sprite_fixture.c "${fixture_header}")
  target_include_directories(sm64ds_sprite_fixture PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  target_link_libraries(sm64ds_sprite_fixture PRIVATE LibSaturn::Saturn)
  libsaturn_configure_executable(sm64ds_sprite_fixture)
  libsaturn_add_binary(sm64ds_sprite_fixture)
  libsaturn_add_disc(sm64ds_sprite_fixture NAME sm64ds_sprite_fixture)
endif()

option(SM64DS_BUILD_CASTLE "Build the playable castle exterior" OFF)
option(SM64DS_VISUAL_DIAGNOSTICS "Enable deterministic visual diagnostic controls" OFF)
set(SM64DS_DIAG_OBJECTS "15" CACHE STRING "Diagnostic object mask: sky=1, castle=2, body=4, head=8")
set(SM64DS_DIAG_CLIP "0" CACHE STRING "Diagnostic frozen clip index")
set(SM64DS_DIAG_FRAME "0" CACHE STRING "Diagnostic frozen animation frame at 30 Hz")
option(SM64DS_DIAG_NO_CULL "Disable face culling for diagnostic captures" OFF)
option(SM64DS_DIAG_SOLID "Replace textures with distinct diagnostic colors" OFF)
option(SM64DS_DIAG_FACE_IDS "Render body faces with individually encoded colors" OFF)
option(SM64DS_DIAG_CASTLE_FACE_IDS "Render castle faces with individually encoded colors" OFF)
option(SM64DS_DIAG_CASTLE_FALLBACK_COLOR "Highlight castle flat clipping fallback in magenta" OFF)
option(SM64DS_DIAG_FIXED_CAMERA "Freeze player and camera at a chosen point for matching captures" OFF)
set(SM64DS_DIAG_X "0" CACHE STRING "Fixed diagnostic player X in world units")
set(SM64DS_DIAG_Z "256" CACHE STRING "Fixed diagnostic player Z in world units")
set(SM64DS_DIAG_FLOOR_CEILING "512" CACHE STRING "Maximum floor height for fixed diagnostic player")
set(SM64DS_DIAG_YAW "180" CACHE STRING "Fixed diagnostic camera yaw in degrees")
option(SM64DS_DIAG_CLOSE_CAMERA "Use close camera for fixed diagnostic captures" ON)
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
  target_compile_definitions(sm64ds_castle PRIVATE
    SM64DS_VISUAL_DIAGNOSTICS=$<BOOL:${SM64DS_VISUAL_DIAGNOSTICS}>
    SM64DS_DIAG_OBJECTS=${SM64DS_DIAG_OBJECTS}
    SM64DS_DIAG_CLIP=${SM64DS_DIAG_CLIP}
    SM64DS_DIAG_FRAME=${SM64DS_DIAG_FRAME}
    SM64DS_DIAG_NO_CULL=$<BOOL:${SM64DS_DIAG_NO_CULL}>
    SM64DS_DIAG_SOLID=$<BOOL:${SM64DS_DIAG_SOLID}>
    SM64DS_DIAG_FACE_IDS=$<BOOL:${SM64DS_DIAG_FACE_IDS}>
    SM64DS_DIAG_CASTLE_FACE_IDS=$<BOOL:${SM64DS_DIAG_CASTLE_FACE_IDS}>
    SM64DS_DIAG_CASTLE_FALLBACK_COLOR=$<BOOL:${SM64DS_DIAG_CASTLE_FALLBACK_COLOR}>
    SM64DS_DIAG_FIXED_CAMERA=$<BOOL:${SM64DS_DIAG_FIXED_CAMERA}>
    SM64DS_DIAG_X=${SM64DS_DIAG_X}
    SM64DS_DIAG_Z=${SM64DS_DIAG_Z}
    SM64DS_DIAG_FLOOR_CEILING=${SM64DS_DIAG_FLOOR_CEILING}
    SM64DS_DIAG_YAW=${SM64DS_DIAG_YAW}
    SM64DS_DIAG_CLOSE_CAMERA=$<BOOL:${SM64DS_DIAG_CLOSE_CAMERA}>)
  target_link_libraries(sm64ds_castle PRIVATE LibSaturn::Saturn)
  libsaturn_configure_executable(sm64ds_castle)
  libsaturn_add_binary(sm64ds_castle)
  libsaturn_add_disc(sm64ds_castle NAME sm64ds_castle)
endif()
