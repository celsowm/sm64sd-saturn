cmake_minimum_required(VERSION 3.24)
project(sm64ds_saturn LANGUAGES C)

# Keep ROM-derived C/H outside the source tree and therefore outside Git.
if(NOT DEFINED SM64DS_GENERATED_DIR OR NOT EXISTS "${SM64DS_GENERATED_DIR}/mario_preview.c")
  message(FATAL_ERROR "Set -DSM64DS_GENERATED_DIR=/private/derived to your locally generated mario_preview.c/.h")
endif()

find_package(LibSaturn 0.1 CONFIG REQUIRED)
add_executable(sm64ds_viewer
  src/viewer.c
  runtime/sm64ds_pose.c
  "${SM64DS_GENERATED_DIR}/mario_preview.c")
target_include_directories(sm64ds_viewer PRIVATE
  "${CMAKE_SOURCE_DIR}/runtime"
  "${SM64DS_GENERATED_DIR}")
target_link_libraries(sm64ds_viewer PRIVATE LibSaturn::Saturn)
libsaturn_configure_executable(sm64ds_viewer)
libsaturn_add_disc(sm64ds_viewer NAME sm64ds_viewer)
