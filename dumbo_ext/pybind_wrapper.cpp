#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "dumbo_batch_encoder.cuh"

namespace py = pybind11;

PYBIND11_MODULE(dumbo_cuda, m) {
    m.doc() = "Dumbo Protocol — OpenFHE NVIDIA GPU HAL bridge";
    py::class_<DumboBatchEncoder>(m, "DumboBatchEncoder")
        .def(py::init<uint32_t, uint64_t>(),
             py::arg("poly_degree") = 1024,
             py::arg("plaintext_mod") = 65537)
        .def("encode_batch", &DumboBatchEncoder::EncodeBatch,
             "CRT-encode a flat list of uint64 state vectors (len must be multiple of N)");
}
