#include "dumbo_batch_encoder.cuh"
#include <stdexcept>
#include <cmath>

// ── GPU kernel ────────────────────────────────────────────────────────────────
__global__ void CRTEncodeKernel(
    uint64_t* __restrict__ d_out,
    const uint64_t* __restrict__ d_in,
    const uint64_t* __restrict__ d_enc_mat,
    uint32_t N, uint64_t T, uint32_t batch)
{
    uint32_t gid = blockIdx.x * blockDim.x + threadIdx.x;
    if (gid >= (uint32_t)batch * N) return;
    uint32_t b = gid / N;
    uint32_t p = gid % N;
    uint64_t acc = 0;
    for (uint32_t j = 0; j < N; ++j) {
        uint64_t v = (__uint128_t)d_in[b*N+j] * d_enc_mat[p*N+j] % T;
        acc = (acc + v) % T;
    }
    d_out[gid] = acc;
}

// ── host helpers ──────────────────────────────────────────────────────────────
uint64_t DumboBatchEncoder::modpow(uint64_t b, uint64_t e, uint64_t m) {
    uint64_t r = 1; b %= m;
    while (e > 0) { if (e&1) r = (__uint128_t)r*b%m; b=(__uint128_t)b*b%m; e>>=1; }
    return r;
}
uint64_t DumboBatchEncoder::bitrev(uint32_t x, int bits) {
    uint64_t r = 0;
    for (int i = 0; i < bits; ++i) { r=(r<<1)|(x&1); x>>=1; }
    return r;
}

void DumboBatchEncoder::precompute_roots() {
    int logN = (int)std::log2(N);
    uint64_t omega = modpow(3, (T-1)/(2*N), T);

    std::vector<uint64_t> roots(N);
    for (uint32_t i = 0; i < N; ++i)
        roots[i] = modpow(omega, 2*bitrev(i,logN)+1, T);

    uint64_t invN = modpow(N, T-2, T);
    std::vector<uint64_t> h_enc(N*N), h_dec(N*N);
    for (uint32_t i = 0; i < N; ++i) {
        for (uint32_t j = 0; j < N; ++j) {
            h_dec[i*N+j] = modpow(roots[i], j, T);
            uint64_t inv_root = modpow(roots[j], T-2, T);
            h_enc[i*N+j] = (__uint128_t)invN * modpow(inv_root, i, T) % T;
        }
    }
    cudaMalloc(&d_enc_mat, N*N*sizeof(uint64_t));
    cudaMalloc(&d_dec_mat, N*N*sizeof(uint64_t));
    cudaMemcpyAsync(d_enc_mat, h_enc.data(), N*N*sizeof(uint64_t), cudaMemcpyHostToDevice, stream);
    cudaMemcpyAsync(d_dec_mat, h_dec.data(), N*N*sizeof(uint64_t), cudaMemcpyHostToDevice, stream);
    cudaStreamSynchronize(stream);
}

// ── constructor / destructor ──────────────────────────────────────────────────
DumboBatchEncoder::DumboBatchEncoder(uint32_t poly_degree, uint64_t plaintext_mod)
    : N(poly_degree), T(plaintext_mod)
{
    cudaStreamCreate(&stream);
    precompute_roots();
}

DumboBatchEncoder::~DumboBatchEncoder() {
    if (d_enc_mat) cudaFree(d_enc_mat);
    if (d_dec_mat) cudaFree(d_dec_mat);
    cudaStreamDestroy(stream);
}

// ── EncodeBatch ───────────────────────────────────────────────────────────────
std::vector<uint64_t> DumboBatchEncoder::EncodeBatch(const std::vector<uint64_t>& h_state) {
    if (h_state.size() % N != 0)
        throw std::invalid_argument("Input size must be a multiple of N");
    uint32_t batch = h_state.size() / N;
    uint32_t total  = batch * N;

    uint64_t *d_in, *d_out;
    cudaMalloc(&d_in,  total * sizeof(uint64_t));
    cudaMalloc(&d_out, total * sizeof(uint64_t));
    cudaMemcpyAsync(d_in, h_state.data(), total*sizeof(uint64_t), cudaMemcpyHostToDevice, stream);

    int threads = 256;
    int blocks  = (total + threads - 1) / threads;
    CRTEncodeKernel<<<blocks, threads, 0, stream>>>(d_out, d_in, d_enc_mat, N, T, batch);

    std::vector<uint64_t> h_out(total);
    cudaMemcpyAsync(h_out.data(), d_out, total*sizeof(uint64_t), cudaMemcpyDeviceToHost, stream);
    cudaStreamSynchronize(stream);

    cudaFree(d_in);
    cudaFree(d_out);
    return h_out;
}
