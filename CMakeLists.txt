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
set(SM64DS_CASTLE_1F_DIR "" CACHE PATH "Optional generated directory for Castle 1F interior (packaged as C1F.BIN)")
option(SM64DS_VISUAL_DIAGNOSTICS "Enable deterministic visual diagnostic controls" OFF)
set(SM64DS_DIAG_OBJECTS "15" CACHE STRING "Diagnostic object mask: sky=1, castle=2, body=4, head=8")
set(SM64DS_DIAG_CLIP "0" CACHE STRING "Diagnostic frozen clip index")
set(SM64DS_DIAG_FRAME "0" CACHE STRING "Diagnostic frozen animation frame at 30 Hz")
option(SM64DS_DIAG_LIVE_ANIMATION "Run gameplay animation during diagnostic captures" OFF)
option(SM64DS_DIAG_GROUND_POSE "Keep a grounded animated body above its collision floor" OFF)
option(SM64DS_DIAG_NO_CULL "Disable face culling for diagnostic captures" OFF)
option(SM64DS_DIAG_SOLID "Replace textures with distinct diagnostic colors" OFF)
option(SM64DS_DIAG_FACE_IDS "Render body faces with individually encoded colors" OFF)
option(SM64DS_DIAG_CASTLE_FACE_IDS "Render castle faces with individually encoded colors" OFF)
option(SM64DS_DIAG_CASTLE_FALLBACK_COLOR "Highlight castle flat clipping fallback in magenta" OFF)
option(SM64DS_DIAG_FIXED_CAMERA "Freeze player and camera at a chosen point for matching captures" OFF)
option(SM64DS_DIAG_OVERRIDE_PLAYER_Y "Override player height in fixed diagnostic captures" OFF)
set(SM64DS_DIAG_PLAYER_Y "0" CACHE STRING "Fixed diagnostic player Y in world units")
option(SM64DS_DIAG_ORBIT_PLAYER "Allow camera input while the diagnostic player stays fixed" OFF)
set(SM64DS_DIAG_FAR_DEPTH_FIRST "0" CACHE STRING "Experimental first castle render face for far-depth test")
set(SM64DS_DIAG_FAR_DEPTH_COUNT "0" CACHE STRING "Experimental number of castle render faces for far-depth test")
option(SM64DS_DIAG_GEOMETRIC_DEPTH "Gate experimental depth adjustments on projected triangle comparisons" OFF)
option(SM64DS_DIAG_PAIR_DEPTH "Experiment with per-body-face depth corrections" OFF)
option(SM64DS_DIAG_SUPPORT_DEPTH "Experiment with ordering flat support ground behind the actor" OFF)
option(SM64DS_DIAG_SUPPORT_GUARD "Preserve potentially overlapping scenery in support-depth experiment" ON)
option(SM64DS_DIAG_SUPPORT_AUTO "Find support-plane candidates from generated source-face metadata" OFF)
option(SM64DS_DIAG_SLOPED_SUPPORT "Experiment with walkable sloped support planes" OFF)
option(SM64DS_DIAG_WALL_FIXTURE "Submit a fixed diagnostic wall at the matched orbit pose" OFF)
option(SM64DS_DIAG_WALL_PARTIAL "Use a narrow diagnostic wall" OFF)
option(SM64DS_DIAG_ABSOLUTE_CAMERA "Use absolute diagnostic eye and target coordinates" OFF)
option(SM64DS_DIAG_DS_ASPECT "Use the DS top screen 4:3 camera aspect in diagnostics" ON)
option(SM64DS_DIAG_SHOW_UI "Show the Saturn control overlay in diagnostic captures" OFF)
set(SM64DS_DIAG_X "0" CACHE STRING "Fixed diagnostic player X in world units")
set(SM64DS_DIAG_Z "256" CACHE STRING "Fixed diagnostic player Z in world units")
set(SM64DS_DIAG_CAMERA_X "0" CACHE STRING "Absolute diagnostic camera eye X in world units")
set(SM64DS_DIAG_CAMERA_Y "48" CACHE STRING "Absolute diagnostic camera eye Y in world units")
set(SM64DS_DIAG_CAMERA_Z "166" CACHE STRING "Absolute diagnostic camera eye Z in world units")
set(SM64DS_DIAG_TARGET_X "0" CACHE STRING "Absolute diagnostic camera target X in world units")
set(SM64DS_DIAG_TARGET_Y "8" CACHE STRING "Absolute diagnostic camera target Y in world units")
set(SM64DS_DIAG_TARGET_Z "256" CACHE STRING "Absolute diagnostic camera target Z in world units")
set(SM64DS_DIAG_CAMERA_DISTANCE "65" CACHE STRING "Fixed diagnostic camera distance in world units")
set(SM64DS_DIAG_FACING "180" CACHE STRING "Fixed diagnostic Mario facing in degrees")
set(SM64DS_DIAG_FOV_Y "60" CACHE STRING "Fixed diagnostic vertical field of view in degrees")
set(SM64DS_DIAG_FLOOR_CEILING "512" CACHE STRING "Maximum floor height for fixed diagnostic player")
set(SM64DS_DIAG_YAW "180" CACHE STRING "Fixed diagnostic camera yaw in degrees")
option(SM64DS_DIAG_CLOSE_CAMERA "Use close camera for fixed diagnostic captures" ON)
if(SM64DS_BUILD_CASTLE)
  if(NOT EXISTS "${SM64DS_GENERATED_DIR}/castle_scene.c")
    message(FATAL_ERROR "Run tools/prepare_castle.py into SM64DS_GENERATED_DIR first")
  endif()
  set(SM64DS_DIAG_EFFECTIVE_FACE_FIRST "${SM64DS_DIAG_FAR_DEPTH_FIRST}")
  set(SM64DS_DIAG_EFFECTIVE_FACE_COUNT "${SM64DS_DIAG_FAR_DEPTH_COUNT}")
  if(SM64DS_DIAG_SUPPORT_AUTO)
    set(SM64DS_DIAG_EFFECTIVE_FACE_FIRST "0")
    set(SM64DS_DIAG_EFFECTIVE_FACE_COUNT "CASTLE_FACE_COUNT")
  endif()
  add_executable(sm64ds_castle src/castle.c runtime/sm64ds_play.c
    runtime/sm64ds_pose.c runtime/sm64ds_background.c runtime/sm64ds_painter.c
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
    SM64DS_DIAG_LIVE_ANIMATION=$<BOOL:${SM64DS_DIAG_LIVE_ANIMATION}>
    SM64DS_DIAG_GROUND_POSE=$<BOOL:${SM64DS_DIAG_GROUND_POSE}>
    SM64DS_DIAG_NO_CULL=$<BOOL:${SM64DS_DIAG_NO_CULL}>
    SM64DS_DIAG_SOLID=$<BOOL:${SM64DS_DIAG_SOLID}>
    SM64DS_DIAG_FACE_IDS=$<BOOL:${SM64DS_DIAG_FACE_IDS}>
    SM64DS_DIAG_CASTLE_FACE_IDS=$<BOOL:${SM64DS_DIAG_CASTLE_FACE_IDS}>
    SM64DS_DIAG_CASTLE_FALLBACK_COLOR=$<BOOL:${SM64DS_DIAG_CASTLE_FALLBACK_COLOR}>
    SM64DS_DIAG_FIXED_CAMERA=$<BOOL:${SM64DS_DIAG_FIXED_CAMERA}>
    SM64DS_DIAG_OVERRIDE_PLAYER_Y=$<BOOL:${SM64DS_DIAG_OVERRIDE_PLAYER_Y}>
    SM64DS_DIAG_PLAYER_Y=${SM64DS_DIAG_PLAYER_Y}
    SM64DS_DIAG_ORBIT_PLAYER=$<BOOL:${SM64DS_DIAG_ORBIT_PLAYER}>
    SM64DS_DIAG_FAR_DEPTH_FIRST=${SM64DS_DIAG_EFFECTIVE_FACE_FIRST}
    SM64DS_DIAG_FAR_DEPTH_COUNT=${SM64DS_DIAG_EFFECTIVE_FACE_COUNT}
    SM64DS_DIAG_GEOMETRIC_DEPTH=$<BOOL:${SM64DS_DIAG_GEOMETRIC_DEPTH}>
    SM64DS_DIAG_PAIR_DEPTH=$<BOOL:${SM64DS_DIAG_PAIR_DEPTH}>
    SM64DS_DIAG_SUPPORT_DEPTH=$<BOOL:${SM64DS_DIAG_SUPPORT_DEPTH}>
    SM64DS_DIAG_SUPPORT_GUARD=$<BOOL:${SM64DS_DIAG_SUPPORT_GUARD}>
    SM64DS_DIAG_SUPPORT_AUTO=$<BOOL:${SM64DS_DIAG_SUPPORT_AUTO}>
    SM64DS_DIAG_SLOPED_SUPPORT=$<BOOL:${SM64DS_DIAG_SLOPED_SUPPORT}>
    SM64DS_DIAG_WALL_FIXTURE=$<BOOL:${SM64DS_DIAG_WALL_FIXTURE}>
    SM64DS_DIAG_WALL_PARTIAL=$<BOOL:${SM64DS_DIAG_WALL_PARTIAL}>
    SM64DS_DIAG_ABSOLUTE_CAMERA=$<BOOL:${SM64DS_DIAG_ABSOLUTE_CAMERA}>
    SM64DS_DIAG_DS_ASPECT=$<BOOL:${SM64DS_DIAG_DS_ASPECT}>
    SM64DS_DIAG_SHOW_UI=$<BOOL:${SM64DS_DIAG_SHOW_UI}>
    SM64DS_DIAG_X=${SM64DS_DIAG_X}
    SM64DS_DIAG_Z=${SM64DS_DIAG_Z}
    SM64DS_DIAG_CAMERA_X=${SM64DS_DIAG_CAMERA_X}
    SM64DS_DIAG_CAMERA_Y=${SM64DS_DIAG_CAMERA_Y}
    SM64DS_DIAG_CAMERA_Z=${SM64DS_DIAG_CAMERA_Z}
    SM64DS_DIAG_TARGET_X=${SM64DS_DIAG_TARGET_X}
    SM64DS_DIAG_TARGET_Y=${SM64DS_DIAG_TARGET_Y}
    SM64DS_DIAG_TARGET_Z=${SM64DS_DIAG_TARGET_Z}
    SM64DS_DIAG_CAMERA_DISTANCE=${SM64DS_DIAG_CAMERA_DISTANCE}
    SM64DS_DIAG_FACING=${SM64DS_DIAG_FACING}
    SM64DS_DIAG_FOV_Y=${SM64DS_DIAG_FOV_Y}
    SM64DS_DIAG_FLOOR_CEILING=${SM64DS_DIAG_FLOOR_CEILING}
    SM64DS_DIAG_YAW=${SM64DS_DIAG_YAW}
    SM64DS_DIAG_CLOSE_CAMERA=$<BOOL:${SM64DS_DIAG_CLOSE_CAMERA}>)
  target_link_libraries(sm64ds_castle PRIVATE LibSaturn::Saturn)
  libsaturn_configure_executable(sm64ds_castle)
  libsaturn_add_binary(sm64ds_castle)
  set(_castle_disc_root_files "")
  set(_castle_disc_deps "")
  if(SM64DS_CASTLE_1F_DIR AND EXISTS "${SM64DS_CASTLE_1F_DIR}/castle_scene.c")
    add_executable(sm64ds_castle_1f src/castle.c runtime/sm64ds_play.c
      runtime/sm64ds_pose.c runtime/sm64ds_background.c runtime/sm64ds_painter.c
      "${SM64DS_CASTLE_1F_DIR}/mario_preview.c"
      "${SM64DS_CASTLE_1F_DIR}/castle_scene.c"
      "${SM64DS_CASTLE_1F_DIR}/mario_head.c")
    target_include_directories(sm64ds_castle_1f PRIVATE runtime "${SM64DS_CASTLE_1F_DIR}")
    target_compile_definitions(sm64ds_castle_1f PRIVATE
      SM64DS_VISUAL_DIAGNOSTICS=0
      SM64DS_DIAG_SHOW_UI=0)
    target_link_libraries(sm64ds_castle_1f PRIVATE LibSaturn::Saturn)
    libsaturn_configure_executable(sm64ds_castle_1f)
    libsaturn_add_binary(sm64ds_castle_1f)
    libsaturn_add_disc(sm64ds_castle_1f NAME sm64ds_castle_1f)
    set(_c1f_bin "${CMAKE_CURRENT_BINARY_DIR}/C1F.BIN")
    add_custom_command(OUTPUT "${_c1f_bin}"
      COMMAND "${CMAKE_COMMAND}" -E copy_if_different
        "${CMAKE_CURRENT_BINARY_DIR}/sm64ds_castle_1f.app.bin" "${_c1f_bin}"
      DEPENDS sm64ds_castle_1f
      COMMENT "Staging C1F.BIN for multi-stage Saturn disc"
      VERBATIM)
    add_custom_target(sm64ds_castle_1f_stage_bin DEPENDS "${_c1f_bin}")
    list(APPEND _castle_disc_root_files "${_c1f_bin}")
    list(APPEND _castle_disc_deps sm64ds_castle_1f_stage_bin)
  endif()
  libsaturn_add_disc(sm64ds_castle NAME sm64ds_castle
    ROOT_FILES ${_castle_disc_root_files}
    DEPENDS ${_castle_disc_deps})
endif()
