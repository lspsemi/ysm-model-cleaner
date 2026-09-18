project(cityhash)
add_library(cityhash STATIC src/city.cc)
target_include_directories(cityhash PUBLIC 
    src
    ${CMAKE_CURRENT_SOURCE_DIR}
)