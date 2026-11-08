// PCIe host<->device bandwidth, one repetition per invocation (WP6).
//
//   pcie_bw --dir h2d|d2h --mem pinned|pageable --bytes N [--iters I] [--series K] [--warmup-s S]
//
// Bulk mode (default): I back-to-back cudaMemcpyAsync of N bytes on one stream, timed as a whole
// with CUDA events. Series mode (--series K): K back-to-back copies of N bytes from/to K distinct
// buffer offsets (an expert-cache-miss pattern), each timed with its own event pair; reports the
// per-copy latency distribution and the throughput of the whole series.
// An untimed warm-up of at least 0.7 s runs first so the link has left its idle state.
// Prints one JSON object on stdout. Bandwidth is decimal GB/s (1e9 bytes/s).
//
// Build: /opt/cuda/bin/nvcc -ccbin /usr/bin/g++ -gencode arch=compute_120,code=sm_120 -O2 \
//        -o build/tools/pcie_bw tools/pcie_bw.cu

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

#include <cuda_runtime.h>

#define CK(call)                                                                          \
  do {                                                                                    \
    cudaError_t e_ = (call);                                                              \
    if (e_ != cudaSuccess) {                                                              \
      fprintf(stderr, "CUDA error %s at %s:%d: %s\n", #call, __FILE__, __LINE__,          \
              cudaGetErrorString(e_));                                                    \
      exit(2);                                                                            \
    }                                                                                     \
  } while (0)

static double epoch_now() {
  timespec ts;
  clock_gettime(CLOCK_REALTIME, &ts);
  return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static void usage() {
  fprintf(stderr,
          "usage: pcie_bw --dir h2d|d2h --mem pinned|pageable --bytes N [--iters I] [--series K] [--warmup-s S]\n");
  exit(64);
}

int main(int argc, char** argv) {
  std::string dir, mem;
  size_t bytes = 0;
  int iters = 0, series = 0;
  double warmup_s = 0.7;
  for (int i = 1; i < argc; i++) {
    std::string a = argv[i];
    auto next = [&]() -> const char* {
      if (i + 1 >= argc) usage();
      return argv[++i];
    };
    if (a == "--dir") dir = next();
    else if (a == "--mem") mem = next();
    else if (a == "--bytes") bytes = strtoull(next(), nullptr, 10);
    else if (a == "--iters") iters = atoi(next());
    else if (a == "--series") series = atoi(next());
    else if (a == "--warmup-s") warmup_s = atof(next());
    else usage();
  }
  if ((dir != "h2d" && dir != "d2h") || (mem != "pinned" && mem != "pageable") || bytes == 0)
    usage();
  if (!series && iters <= 0) iters = (int)std::max<size_t>(8, (size_t)4e9 / bytes);
  const bool h2d = dir == "h2d";
  const bool pinned = mem == "pinned";

  int dev = 0;
  CK(cudaSetDevice(dev));
  cudaDeviceProp prop;
  CK(cudaGetDeviceProperties(&prop, dev));
  int rt = 0;
  CK(cudaRuntimeGetVersion(&rt));

  const size_t slots = series ? (size_t)series : 1;
  const size_t total = bytes * slots;
  void* host = nullptr;
  if (pinned) {
    CK(cudaMallocHost(&host, total));
  } else {
    host = malloc(total);
    if (!host) { fprintf(stderr, "malloc failed\n"); return 2; }
  }
  memset(host, 0x5a, total);  // touch every page: pageable memory must be resident
  void* devp = nullptr;
  CK(cudaMalloc(&devp, total));
  CK(cudaMemset(devp, 0, total));

  cudaStream_t st;
  CK(cudaStreamCreate(&st));
  auto copy = [&](size_t off) {
    char* h = (char*)host + off;
    char* d = (char*)devp + off;
    if (h2d) CK(cudaMemcpyAsync(d, h, bytes, cudaMemcpyHostToDevice, st));
    else CK(cudaMemcpyAsync(h, d, bytes, cudaMemcpyDeviceToHost, st));
  };

  // Untimed warm-up: keep the link busy for at least --warmup-s seconds (default 0.7), so the
  // link has left its idle state and a 2 Hz sampler sees it under load.
  const double t_active0 = epoch_now();
  {
    size_t i = 0;
    do {
      for (int k = 0; k < 16; k++, i++) copy((i % slots) * bytes);
      CK(cudaStreamSynchronize(st));
    } while (epoch_now() - t_active0 < warmup_s);
  }

  printf("{\"gpu\":\"%s\",\"cuda_runtime\":%d,\"dir\":\"%s\",\"mem\":\"%s\",\"bytes\":%zu,",
         prop.name, rt, dir.c_str(), mem.c_str(), bytes);

  double t0, t1;
  if (!series) {
    cudaEvent_t a, b;
    CK(cudaEventCreate(&a));
    CK(cudaEventCreate(&b));
    t0 = epoch_now();
    CK(cudaEventRecord(a, st));
    for (int i = 0; i < iters; i++) copy(0);
    CK(cudaEventRecord(b, st));
    CK(cudaEventSynchronize(b));
    t1 = epoch_now();
    float ms = 0;
    CK(cudaEventElapsedTime(&ms, a, b));
    double gbps = (double)bytes * iters / (ms * 1e-3) / 1e9;
    printf("\"mode\":\"bulk\",\"iters\":%d,\"elapsed_ms\":%.4f,\"gb_per_s\":%.4f,", iters, ms, gbps);
  } else {
    std::vector<cudaEvent_t> ev(slots + 1);
    for (auto& e : ev) CK(cudaEventCreate(&e));
    t0 = epoch_now();
    CK(cudaEventRecord(ev[0], st));
    for (size_t i = 0; i < slots; i++) {
      copy(i * bytes);
      CK(cudaEventRecord(ev[i + 1], st));
    }
    CK(cudaEventSynchronize(ev[slots]));
    t1 = epoch_now();
    std::vector<double> lat(slots);  // microseconds; copy i runs between ev[i] and ev[i+1]
    for (size_t i = 0; i < slots; i++) {
      float ms = 0;
      CK(cudaEventElapsedTime(&ms, ev[i], ev[i + 1]));
      lat[i] = ms * 1e3;
    }
    float total_ms = 0;
    CK(cudaEventElapsedTime(&total_ms, ev[0], ev[slots]));
    std::vector<double> s = lat;
    std::sort(s.begin(), s.end());
    double sum = 0;
    for (double v : lat) sum += v;
    auto pct = [&](double p) { return s[std::min(s.size() - 1, (size_t)(p * s.size()))]; };
    printf("\"mode\":\"series\",\"copies\":%zu,\"elapsed_ms\":%.4f,\"gb_per_s\":%.4f,"
           "\"latency_us\":{\"mean\":%.3f,\"min\":%.3f,\"p50\":%.3f,\"p95\":%.3f,\"max\":%.3f},",
           slots, total_ms, (double)bytes * slots / (total_ms * 1e-3) / 1e9, sum / slots, s.front(),
           pct(0.5), pct(0.95), s.back());
  }
  printf("\"t_active_start\":%.3f,\"t_timed_start\":%.3f,\"t_end\":%.3f}\n", t_active0, t0, t1);

  CK(cudaStreamDestroy(st));
  CK(cudaFree(devp));
  if (pinned) CK(cudaFreeHost(host)); else free(host);
  return 0;
}
