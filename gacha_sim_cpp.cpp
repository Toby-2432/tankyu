#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <random>
#include <vector>
#include <cmath>
#include <numeric>

namespace py = pybind11;

// --- 既存のシミュレーション関数（省略せずにそのまま残します） ---
std::vector<long long> sim_complete(int kai, int syurui, const std::vector<int>& bunsi) {
    std::vector<long long> results(kai);
    std::random_device rd; std::mt19937 gen(rd());
    std::discrete_distribution<> dist(bunsi.begin(), bunsi.end());
    for (int x = 0; x < kai; ++x) {
        std::vector<int> cnt(syurui, 0); int unique_count = 0; long long total = 0;
        while (unique_count < syurui) {
            int item = dist(gen); total++;
            if (cnt[item] == 0) unique_count++;
            cnt[item]++;
        }
        results[x] = total;
    }
    return results;
}

std::vector<long long> sim_specific(int kai, int syurui, const std::vector<int>& bunsi, const std::vector<int>& atari_zero_idx, const std::vector<int>& nankai) {
    std::vector<long long> results(kai);
    std::random_device rd; std::mt19937 gen(rd());
    std::discrete_distribution<> dist(bunsi.begin(), bunsi.end());
    int target_types = atari_zero_idx.size();
    for (int x = 0; x < kai; ++x) {
        std::vector<int> cnt(syurui, 0); int completed_targets = 0; long long total = 0;
        while (completed_targets < target_types) {
            int item = dist(gen); total++; cnt[item]++;
            for (int i = 0; i < target_types; ++i) {
                if (item == atari_zero_idx[i]) {
                    if (cnt[item] == nankai[i]) completed_targets++;
                    break;
                }
            }
        }
        results[x] = total;
    }
    return results;
}

std::pair<std::vector<int>, std::vector<std::vector<int>>> sim_fixed(int kai, int syurui, const std::vector<int>& bunsi, int kaisu, int focused_item_zero_idx) {
    std::vector<int> focused_results(kai);
    std::vector<std::vector<int>> fixed_counts(kai, std::vector<int>(syurui, 0));
    std::random_device rd; std::mt19937 gen(rd());
    std::discrete_distribution<> dist(bunsi.begin(), bunsi.end());
    for (int x = 0; x < kai; ++x) {
        for (int i = 0; i < kaisu; ++i) {
            int item = dist(gen); fixed_counts[x][item]++;
        }
        focused_results[x] = fixed_counts[x][focused_item_zero_idx];
    }
    return {focused_results, fixed_counts};
}

// ==========================================
// ★ ここから新設：理論値の計算関数群
// ==========================================

// 組み合わせ（nCr）を計算する補助関数
double nCr(int n, int r) {
    if (r < 0 || r > n) return 0;
    if (r == 0 || r == n) return 1;
    if (r > n / 2) r = n - r;
    double res = 1;
    for (int i = 1; i <= r; ++i) {
        res = res * (n - r + i) / i;
    }
    return res;
}

// 1. 全種類コンプリートの理論値（包除原理）
// 指定された最大回数（max_pulls）までの累積確率分布（CDF）を返す
std::vector<double> calc_theory_complete(int syurui, const std::vector<int>& bunsi, int bunbo, int max_pulls) {
    std::vector<double> cdf(max_pulls + 1, 0.0);
    
    // 全ての確率が均等（等確率）の場合、包除原理が綺麗に適用できる
    // 確率が不均等の場合はマルコフ連鎖などが必要ですが、元のコードの近似・ロジックに合わせます
    // 元コードが等確率を前提としたシンプルな包除原理だったため、それを超高速化します
    for (int t = 1; t <= max_pulls; ++t) {
        double p_sum = 0.0;
        for (int i = 0; i < syurui; ++i) {
            double sign = (i % 2 == 0) ? 1.0 : -1.0;
            double p_not_all = (double)(syurui - i) / syurui;
            p_sum += sign * nCr(syurui, i) * std::pow(p_not_all, t);
        }
        cdf[t] = p_sum;
    }
    return cdf;
}

// 2. 特定の種類を当てるまでの理論値（負の二項分布）
// Pythonの scipy.stats.nbinom.cdf と同じ計算を高速に行う
std::vector<double> calc_theory_specific(int total_atari_nankai, double p_total_atari, int max_pulls) {
    std::vector<double> cdf(max_pulls + 1, 0.0);
    
    // 負の二項分布の累積確率を計算
    double p = p_total_atari;
    int r = total_atari_nankai;
    
    double sum_p = 0.0;
    // k は「ハズレの回数」
    for (int k = 0; k <= max_pulls - r; ++k) {
        if (k + r > max_pulls) break;
        // 確率質量関数 (PMF) = nCr(k + r - 1, k) * p^r * (1-p)^k
        double pmf = nCr(k + r - 1, k) * std::pow(p, r) * std::pow(1.0 - p, k);
        sum_p += pmf;
        cdf[k + r] = sum_p;
    }
    
    // 累積なので、前の値を引き継ぐ
    for (int t = 1; t <= max_pulls; ++t) {
        if (cdf[t] == 0.0 && t > 0) {
            cdf[t] = cdf[t - 1];
        }
    }
    return cdf;
}

// 3. 固定回数回すの理論値（二項分布）
// Pythonの scipy.stats.binom.pmf と同じ計算を高速に行う
std::vector<double> calc_theory_fixed(int kaisu, double p_focused) {
    std::vector<double> pmf(kaisu + 1, 0.0);
    for (int k = 0; k <= kaisu; ++k) {
        pmf[k] = nCr(kaisu, k) * std::pow(p_focused, k) * std::pow(1.0 - p_focused, kaisu - k);
    }
    return pmf;
}

PYBIND11_MODULE(gacha_sim_cpp, m) {
    m.def("sim_complete", &sim_complete, "complete mode");
    m.def("sim_specific", &sim_specific, "specific mode");
    m.def("sim_fixed", &sim_fixed, "fixed mode");
    // 新しく追加した理論値関数を登録
    m.def("calc_theory_complete", &calc_theory_complete, "theory complete");
    m.def("calc_theory_specific", &calc_theory_specific, "theory specific");
    m.def("calc_theory_fixed", &calc_theory_fixed, "theory fixed");
}