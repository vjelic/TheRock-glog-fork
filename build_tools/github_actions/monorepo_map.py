"""
This dictionary is used to map specific file directory changes to the corresponding build flag and tests
"""
monorepo_map = {
    "projects/hipcub": {
        "flag": "-DTHEROCK_ENABLE_PRIM=ON",
        "test": "test_hipcub"
    },
    "projects/rocprim": {
        "flag": "-DTHEROCK_ENABLE_PRIM=ON",
        "test": "test_rocprim"
    },
    "projects/rocthrust": {
        "flag": "-DTHEROCK_ENABLE_PRIM=ON",
        "test": "test_rocthrust"
    }
}
