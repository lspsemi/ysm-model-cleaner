project(base64)
add_library(base64 STATIC base64.cpp)
target_include_directories(base64 PUBLIC 
    ${CMAKE_CURRENT_SOURCE_DIR}
)