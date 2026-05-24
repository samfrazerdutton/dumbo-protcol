#pragma once
#include "../engine_src/include/cuda_hal.h"
#include "../engine_src/include/shadow_registry.h"
#include <vector>
#include <cstdint>
#include <cuda_runtime.h>

using namespace openfhe_cuda;

class DumboBatchEncoder {
private:
    uint64_t* d_enc_mat = nullptr;
    uint64_t* d_dec_mat = nullptr;
    uint32_t  N;
    uint64_t  T;
    cudaStream_t stream;

    uint64_t modpow(uint64_t base, uint64_t exp, uint64_t mod);
    uint64_t bitrev(uint32_t x, int bits);
    void     precompute_roots();

public:
    DumboBatchEncoder(uint32_t poly_degree, uint64_t plaintext_mod);
    ~DumboBatchEncoder();
    std::vector<uint64_t> EncodeBatch(const std::vector<uint64_t>& h_state);
};
