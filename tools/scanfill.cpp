// Even-odd scanline fill of up to 32 closed polygons into one uint32 label raster.
// Pixel (r, c) is inside polygon b when its centre (c + 0.5, r + 0.5) is inside; bit b of label[r*W + c] is set.
// Method: every edge crossing of a scanline centre toggles bit b at the first column whose centre lies right of the
// crossing; a prefix XOR along each row then gives the labels. Cost: O(scanline crossings + W*H).
#include <atomic>
#include <cmath>
#include <cstdint>
#include <thread>
#include <vector>

extern "C" int sf_fill(int ncurves, const int64_t* offsets, const double* xy, int W, int H, uint32_t* label,
                       int threads) {
    // xy holds pixel-space vertices for all curves back to back; curve b is vertices offsets[b]..offsets[b+1]-1.
    std::vector<std::thread> pool;
    std::atomic<int> next{0};
    auto work = [&]() {
        for (;;) {
            int b = next.fetch_add(1);
            if (b >= ncurves) return;
            const uint32_t bit = 1u << b;
            const int64_t a = offsets[b], e = offsets[b + 1], n = e - a;
            for (int64_t i = 0; i < n; ++i) {
                const double* p = xy + 2 * (a + i);
                const double* q = xy + 2 * (a + (i + 1) % n);
                double x0 = p[0], y0 = p[1], x1 = q[0], y1 = q[1];
                if (y0 == y1) continue;
                if (y0 > y1) { std::swap(x0, x1); std::swap(y0, y1); }
                // scanline centres yc = r + 0.5 with y0 <= yc < y1
                int r0 = (int)std::ceil(y0 - 0.5), r1 = (int)std::ceil(y1 - 0.5);
                if (r0 < 0) r0 = 0;
                if (r1 > H) r1 = H;
                const double slope = (x1 - x0) / (y1 - y0);
                for (int r = r0; r < r1; ++r) {
                    double x = x0 + (r + 0.5 - y0) * slope;
                    long c = (long)std::ceil(x - 0.5);
                    if (c >= W) continue;
                    if (c < 0) c = 0;
                    __atomic_fetch_xor(label + (int64_t)r * W + c, bit, __ATOMIC_RELAXED);
                }
            }
        }
    };
    for (int t = 0; t < threads; ++t) pool.emplace_back(work);
    for (auto& t : pool) t.join();
    // prefix XOR along rows, in parallel over row bands
    pool.clear();
    std::atomic<int> row{0};
    auto scan = [&]() {
        for (;;) {
            int r = row.fetch_add(64);
            if (r >= H) return;
            int re = r + 64 < H ? r + 64 : H;
            for (int rr = r; rr < re; ++rr) {
                uint32_t acc = 0;
                uint32_t* L = label + (int64_t)rr * W;
                for (int c = 0; c < W; ++c) { acc ^= L[c]; L[c] = acc; }
            }
        }
    };
    for (int t = 0; t < threads; ++t) pool.emplace_back(scan);
    for (auto& t : pool) t.join();
    return 0;
}
