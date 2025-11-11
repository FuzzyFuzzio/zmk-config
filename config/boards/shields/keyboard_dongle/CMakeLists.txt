# Add include directory for fallback peripheral count header
target_include_directories(app PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../../../include)
# Force include the fallback header before compiling any sources
target_compile_options(app PRIVATE -include zmk_split_peripheral_count.h)
