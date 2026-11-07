import streamlit as st
import random
import math
import pandas as pd
from datetime import datetime
from scipy.stats import nbinom, binom, chisquare, ttest_1samp
import gacha_sim_cpp
import time

# ページ全体の基本設定
st.set_page_config(page_title="ガチャ・シミュレーター", layout="wide")

st.title("🎯 ガチャ確率シミュレーター ＆ 探究ツール")

# ==========================================
# サイドバー：設定項目の入力エリア
# ==========================================
st.sidebar.header("⚙️ シミュレーション設定")

syurui = st.sidebar.number_input("ガチャの全種類数 (n)", min_value=1, value=10, step=1)

mode = st.sidebar.selectbox(
    "シミュレーションの目的",
    ("全種類コンプリートするまで", "特定の種類を当てるまで", "固定回数回す")
)

st.sidebar.subheader("📈 統計のしきい値設定")
if mode in ["全種類コンプリートするまで", "特定の種類を当てるまで"]:
    target_k = st.sidebar.slider(
        "目標達成確率 K (%)", 
        min_value=0.5, 
        max_value=99.9, 
        value=99.0, 
        step=0.5,
        help="全体の何%の人がガチャを引き終える回数（パーセンタイル）を算出するかを設定します。"
    )
else:
    target_k = st.sidebar.slider(
        "安心の当選確率 K (%)", 
        min_value=0.5, 
        max_value=99.9, 
        value=90.0, 
        step=0.5,
        help="全体の何%の人が「最低でもこの回数以上当選する」というライン（パーセンタイル）を設定します。"
    )

st.sidebar.subheader("🎲 確率の設定")
kakuritu_type = st.sidebar.radio("確率の偏り", ("すべての種類が均等（同じ確率）", "種類ごとに確率が違う（不均等）"))

bunbo = st.sidebar.number_input("確率の分母", min_value=syurui, value=syurui, step=1)

bunsi = []
if kakuritu_type == "すべての種類が均等（同じ確率）":
    base_prob = bunbo // syurui
    bunsi = [base_prob] * syurui
    st.sidebar.info(f"すべての種類が {base_prob}/{bunbo} の確率で排出されます。")
else:
    st.sidebar.write("各種類の分子（確率）を入力してください:")
    df_default = pd.DataFrame({
        "種類": [f"{i+1}番目" for i in range(syurui)],
        "分子": [1] * syurui
    })
    edited_df = st.sidebar.data_editor(df_default, hide_index=True, use_container_width=True, key="prob_editor")
    bunsi = edited_df["分子"].tolist()
    
    if sum(bunsi) != bunbo:
        st.sidebar.error(f"⚠️ 分子の合計({sum(bunsi)})が分母({bunbo})と一致しません！")

atari = []
nankai = []
kaisu = 0
focused_item = 1

if mode == "特定の種類を当てるまで":
    st.sidebar.subheader("🎯 ターゲットの設定")
    nansyu = st.sidebar.number_input("当てたい種類数", min_value=1, max_value=syurui, value=1, step=1)
    
    df_target_default = pd.DataFrame({
        "種類番号(1～)": [i+1 for i in range(nansyu)],
        "目標当選回数": [1] * nansyu
    })
    st.sidebar.write("どの種類を、何回当てたいですか？")
    edited_target_df = st.sidebar.data_editor(df_target_default, hide_index=True, use_container_width=True, key="target_editor")
    
    atari = edited_target_df["種類番号(1～)"].tolist()
    nankai = edited_target_df["目標当選回数"].tolist()
    
    if any(t < 1 or t > syurui for t in atari):
        st.sidebar.error(f"⚠️ 種類番号には 1 から {syurui} までの数字を入力してください！")
    if len(atari) != len(set(atari)):
        st.sidebar.error("⚠️ 同じ種類番号が重複して選ばれています！")

elif mode == "固定回数回す":
    st.sidebar.subheader("🔢 ガチャを回す回数の設定")
    kaisu = st.sidebar.number_input("1回の試行でガチャを何回回すか", min_value=1, value=100, step=10)
    st.sidebar.subheader("🎯 詳しく分析するアイテム")
    focused_item = st.sidebar.number_input(f"確率を絞り込む種類番号 (1～{syurui})", min_value=1, max_value=syurui, value=1, step=1)

st.sidebar.subheader("🔄 シミュレーション回数")
kai = st.sidebar.number_input("この実験を何回繰り返すか", min_value=1, max_value=1000000000000, value=1000, step=100)


# ==========================================
# メイン画面：実行ボタンと計算ロジック
# ==========================================
if st.button("🚀 シミュレーションを実行する", type="primary"):
    
    if sum(bunsi) != bunbo:
        st.error("分子の合計が分母と一致していないため実行できません。サイドバーの設定を確認してください。")
        st.stop()

    progress_text = "シミュレーション実行中... しばらくお待ちください。"
    my_bar = st.progress(0, text=progress_text)
    
    results_history = []
    fixed_mode_counts = []
    focused_results = []
    
    log_lines = []
    log_lines.append(f"=== ガチャ確率シミュレーション詳細ログ ===")
    log_lines.append(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_lines.append(f"シミュレーションモード: {mode}")
    log_lines.append(f"総試行回数: {kai}回")
    log_lines.append(f"しきい値確率(K): {target_k}%")
    log_lines.append("----------------------------------------\n")
    
    steps = 100
    step_kai = kai // steps
    amari = kai % steps

    for s in range(steps):
        current_kai = step_kai + (amari if s == steps - 1 else 0)
        if current_kai <= 0:
            continue
            
        if mode == "全種類コンプリートするまで":
            res = gacha_sim_cpp.sim_complete(current_kai, syurui, bunsi)
            results_history.extend(res)
            
        elif mode == "特定の種類を当てるまで":
            atari_zero = [a - 1 for a in atari]
            res = gacha_sim_cpp.sim_specific(current_kai, syurui, bunsi, atari_zero, nankai)
            results_history.extend(res)
            
        elif mode == "固定回数回す":
            focused_zero = focused_item - 1
            f_res, f_counts = gacha_sim_cpp.sim_fixed(current_kai, syurui, bunsi, kaisu, focused_zero)
            focused_results.extend(f_res)
            fixed_mode_counts.extend(f_counts)

        percent = int((s + 1) / steps * 100)
        my_bar.progress((s + 1) / steps, text=f"シミュレーション実行中... {percent}%完了")
        time.sleep(0.02)
        
    my_bar.empty()
    st.success(f"🎉 {kai}回のシミュレーションが完了しました！")
    st.divider()

    # ==========================================
    # 結果の集計と表示（モード別分岐）
    # ==========================================
    if mode in ["全種類コンプリートするまで", "特定の種類を当てるまで"]:
        indexed_results = [(val, idx) for idx, val in enumerate(results_history)]
        indexed_results.sort(key=lambda x: x[0])
        
        avg_calc = sum(results_history) / kai
        max_calc = indexed_results[-1][0]
        max_idx = indexed_results[-1][1]
        min_calc = indexed_results[0][0]
        min_idx = indexed_results[0][1]
        
        k_fraction = target_k / 100.0
        results_history.sort()
        idx_k = int(kai * k_fraction) - 1 if kai >= 2 else 0
        val_k = results_history[idx_k]

        theo_avg = None
        is_avg_calculable = False
        theo_k = None
        theo_formula_text = ""

        if mode == "全種類コンプリートするまで":
            if kakuritu_type == "すべての種類が均等（同じ確率）":
                harmonic_sum = sum(1 / i for i in range(1, syurui + 1))
                theo_avg = syurui * harmonic_sum
                is_avg_calculable = True
                
                if syurui > 1:
                    bunsi_log = math.log(1 - (k_fraction ** (1 / syurui)))
                    bunbo_log = math.log((syurui - 1) / syurui)
                    theo_k = bunsi_log / bunbo_log
                    theo_formula_text = f"$\\ln(1 - K^{{1/n}}) / \\ln((n-1)/n)$ （$K={k_fraction}$, $n={syurui}$）"
            else:
                if syurui <= 20:
                    p_list = [b / bunbo for b in bunsi]
                    theo_avg = 0.0
                    subsets_p_sum = []
                    subsets_sign = []
                    
                    for i in range(1, 1 << syurui):
                        p_sum = 0.0
                        size = 0
                        for j in range(syurui):
                            if (i >> j) & 1:
                                p_sum += p_list[j]
                                size += 1
                        sign = 1 if size % 2 != 0 else -1
                        theo_avg += sign / p_sum
                        subsets_p_sum.append(p_sum)
                        subsets_sign.append(sign)
                        
                    is_avg_calculable = True
                    
                    def get_comp_prob(t):
                        p_gt_t = 0.0
                        for p_sum, sign in zip(subsets_p_sum, subsets_sign):
                            if 1.0 - p_sum > 0:
                                p_gt_t += sign * ((1.0 - p_sum) ** t)
                        return 1.0 - p_gt_t

                    low = 0.0
                    high = float(theo_avg * 100) + 1000.0
                    for _ in range(50):
                        mid = (low + high) / 2.0
                        if get_comp_prob(mid) >= k_fraction:
                            high = mid
                        else:
                            low = mid
                    theo_k = high
                    theo_formula_text = f"包除原理による累積分布関数 ＋ 二分探索による逆算（種類数 $n={syurui}$）"

        elif mode == "特定の種類を当てるまで":
            if nansyu == 1:
                p = bunsi[atari[0] - 1] / bunbo
                if p > 0:
                    theo_avg = nankai[0] / p
                    is_avg_calculable = True
                
                r = nankai[0]
                if 0 < p < 1:
                    failures = nbinom.ppf(k_fraction, r, p)
                    theo_k = failures + r
                    if r == 1:
                        theo_formula_text = f"$\\ln(1 - K) / \\ln(1 - p)$ （$K={k_fraction}$, $p={p:.4f}$）"
                    else:
                        theo_formula_text = f"負の二項分布の逆累積分布関数 （$K={k_fraction}$, 目標={r}回, $p={p:.4f}$）"
            
            elif all(n == 1 for n in nankai):
                if nansyu <= 14:
                    target_idx = [a - 1 for a in atari]
                    p_list = [bunsi[i] / bunbo for i in range(syurui)]
                    theo_avg = 0.0
                    subsets_p_sum = []
                    subsets_sign = []
                    
                    for i in range(1, 1 << nansyu):
                        p_sum = 0.0
                        size = 0
                        for j in range(nansyu):
                            if (i >> j) & 1:
                                p_sum += p_list[target_idx[j]]
                                size += 1
                        sign = 1 if size % 2 != 0 else -1
                        theo_avg += sign / p_sum
                        subsets_p_sum.append(p_sum)
                        subsets_sign.append(sign)
                        
                    is_avg_calculable = True
                    
                    def get_target_prob(t):
                        p_gt_t = 0.0
                        for p_sum, sign in zip(subsets_p_sum, subsets_sign):
                            if 1.0 - p_sum > 0:
                                p_gt_t += sign * ((1.0 - p_sum) ** t)
                        return 1.0 - p_gt_t

                    low = 0.0
                    high = float(theo_avg * 100) + 1000.0
                    for _ in range(50):
                        mid = (low + high) / 2.0
                        if get_target_prob(mid) >= k_fraction:
                            high = mid
                        else:
                            low = mid
                    theo_k = high
                    theo_formula_text = f"ターゲット限定・包除原理 ＋ 二分探索逆算（ターゲット数 $m={nansyu}$）"

        st.subheader("📊 実測データまとめ")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("平均回数（実測値）", f"{avg_calc:.1f} 回")
        col2.metric("下振れ（最短記録）", f"{min_calc} 回")
        col3.metric("上振れ（最長沼）", f"{max_calc} 回")
        col4.metric(f"実測：{target_k}% ライン", f"{val_k} 回")

        st.divider()

        st.subheader("🔍 ① 平均回数（理論上の期待値）との答え合わせ")
        col_a1, col_a2, col_a3 = st.columns(3)
        col_a1.metric("🏃 実測の平均値", f"{avg_calc:.2f} 回")
        
        if is_avg_calculable and theo_avg is not None:
            col_a2.metric("💡 公式による理論上の期待値", f"{theo_avg:.2f} 回")
            gosa_avg = abs(theo_avg - avg_calc) / theo_avg * 100
            col_a3.metric("📉 平均値の誤差", f"{gosa_avg:.2f} %")
        else:
            col_a2.metric("💡 公式による理論上の期待値", "計算困難")
            col_a3.metric("📉 平均値の誤差", "---")

        st.divider()

        st.subheader(f"🎯 ② 目標達成確率 {target_k}% ラインの答え合わせ")
        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("🎯 実験による実測値", f"{val_k} 回")
        
        if theo_k is not None:
            col_t2.metric("💡 数式による理論値", f"{theo_k:.2f} 回")
            gosa_k = abs(theo_k - val_k) / theo_k * 100
            col_t3.metric("📉 理論値との誤差", f"{gosa_k:.2f} %")
            st.caption(f"※使用した理論式: {theo_formula_text}")
        else:
            col_t2.metric("💡 数式による理論値", "計算困難")
            col_t3.metric("📉 理論値との誤差", "---")

        st.divider()
        st.subheader("🧪 導出理論式（K%ライン）の仮説検定")

        if theo_k is not None:
            target_k_draws = int(round(theo_k))
            success_count = sum(1 for r in results_history if r <= target_k_draws)
            failure_count = kai - success_count
            
            obs = [success_count, failure_count]
            exp = [kai * k_fraction, kai * (1.0 - k_fraction)]
            
            chi2_stat, p_val = chisquare(f_obs=obs, f_exp=exp)
            success_rate = (success_count / kai) * 100
            
            col_k1, col_k2, col_c3 = st.columns(3)
            col_k1.metric("理論達成回数での実測達成率", f"{success_rate:.2f} %", delta=f"{success_rate - target_k:.2f}%")
            col_k2.metric("カイ二乗統計量 ($\chi^2$)", f"{chi2_stat:.4f}")
            col_c3.metric("p値 (p-value)", f"{p_val:.4e}" if p_val < 0.0001 else f"{p_val:.4f}")

            if p_val >= 0.05:
                st.success(f"✅ **判定: 導出した理論式は妥当です（有意差なし、p ≧ 0.05）**\n\n"
                           f"理論式が示す `{target_k_draws}` 回以下で達成した割合（実測: `{success_rate:.2f}%`）は、"
                           f"設定された目標値 `{target_k}%` と統計的に一致しており、導出された理論式は正しいと考えられます。")
            else:
                st.warning(f"⚠️ **判定: 理論式と実測値に統計的な差が検出されました（p < 0.05）**")
            
            with st.expander("ℹ️ この検定の仕組みと解釈について"):
                st.write(f"""
                - **帰無仮説 ($H_0$)**: 導出した理論式による予測（{target_k}%）と実測された成功割合に差はない。
                - **対立仮説 ($H_1$)**: 導出した理論式による予測と実測値に差がある（理論式が不適切）。
                - 理論式から導かれた回数 **{target_k_draws} 回** の時点で、全 {kai} 回の試行中 **{success_count} 回** が達成（実測 **{success_rate:.2f}%**）されました。
                """)
        else:
            st.info("※ 理論式（theo_k）が「計算困難」のため、仮説検定はスキップされました。")

        st.divider()
        st.subheader("📈 かかった回数の分布（沼の可視化）")
        freq = pd.Series(results_history).value_counts().sort_index()
        st.bar_chart(freq, color="#ff4b4b", height=350)

    else:
        # ==========================================
        # 💥 固定回数モードの検証エリア
        # ==========================================
        focused_results.sort()
        k_fraction = target_k / 100.0
        
        avg_fixed = sum(focused_results) / kai
        min_fixed = focused_results[0]
        max_fixed = focused_results[-1]
        
        idx_k_fixed = int(kai * (1.0 - k_fraction))
        if idx_k_fixed >= kai: idx_k_fixed = kai - 1
        val_k_fixed = focused_results[idx_k_fixed]
        
        p_fixed = bunsi[focused_item - 1] / bunbo
        theo_avg_fixed = kaisu * p_fixed
        theo_k_fixed = binom.ppf(1.0 - k_fraction, kaisu, p_fixed)

        st.subheader(f"📊 アイテム [{focused_item}番目] の実測データまとめ（1回あたり {kaisu} 回ガチャ × {kai} 回実験）")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("平均当選回数（実測）", f"{avg_fixed:.2f} 回")
        col2.metric("下振れ（最小当選数）", f"{min_fixed} 回")
        col3.metric("上振れ（最大当選数）", f"{max_fixed} 回")
        col4.metric(f"実測：{target_k}% 安心ライン", f"{val_k_fixed} 回")

        st.divider()
        st.subheader("🔍 ① 平均当選回数（理論上の期待値）との答え合わせ")
        col_a1, col_a2, col_a3 = st.columns(3)
        col_a1.metric("🏃 実測の平均値", f"{avg_fixed:.2f} 回")
        col_a2.metric("💡 公式による理論上の期待値", f"{theo_avg_fixed:.2f} 回")
        gosa_avg_fixed = abs(theo_avg_fixed - avg_fixed) / theo_avg_fixed * 100 if theo_avg_fixed > 0 else 0
        col_a3.metric("📉 平均値の誤差", f"{gosa_avg_fixed:.2f} %")

        # ==========================================
        # 🧪 🎯 初回達成率（初めて当たる確率）の仮説検定
        # ==========================================
        st.divider()
        st.subheader(f"🧪 ［{focused_item}番目］の「初回達成率（初めて当たる確率）」に関する仮説検定")

        # 1回の実験（N回ガチャ）で「少なくとも1回以上当たる確率」 P(>=1) = 1 - (1-p)^N
        p_at_least_1_theo = 1.0 - ((1.0 - p_fixed) ** kaisu)
        
        # 実測データ：1回目の実験（最初のN回）で初めて当たった試行数
        # focused_results は各実験（N回ガチャ）での当選回数リスト。最初（1回目）の実験で当たった＝focused_results[0] >= 1
        # 全体(kai回)の中で「1回目の実験で成功した割合（初回達成率）」をカウント
        first_try_success = sum(1 for r in focused_results if r >= 1)
        first_try_fail = kai - first_try_success
        
        real_first_rate = (first_try_success / kai) * 100
        theo_first_rate = p_at_least_1_theo * 100
        
        # カイ二乗適合度検定（観測値 vs 理論確率）
        obs_first = [first_try_success, first_try_fail]
        exp_first = [kai * p_at_least_1_theo, kai * (1.0 - p_at_least_1_theo)]
        
        chi2_first, p_val_first = chisquare(f_obs=obs_first, f_exp=exp_first)

        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        col_h1.metric("💡 理論上の初回達成率", f"{theo_first_rate:.2f} %")
        col_h2.metric("🏃 実測の初回達成率", f"{real_first_rate:.2f} %", delta=f"{real_first_rate - theo_first_rate:.2f}%")
        col_h3.metric("カイ二乗統計量 ($\chi^2$)", f"{chi2_first:.4f}")
        col_h4.metric("p値 (p-value)", f"{p_val_first:.4e}" if p_val_first < 0.0001 else f"{p_val_first:.4f}")

        if p_val_first >= 0.05:
            st.success(f"✅ **判定: 導出した理論式（初回達成率: 約{theo_first_rate:.1f}%）は妥当です（p ≧ 0.05）**\n\n"
                       f"全 {kai} 回の実験中、最初の {kaisu} 回以内で初めて当たる割合（実測: `{real_first_rate:.2f}%`）は"
                       f"幾何分布/余事象から求めた理論値（`{theo_first_rate:.2f}%`）と統計的に一致しており、導出式は正しいと考えられます。")
        else:
            st.warning(f"⚠️ **判定: 理論確率と実測結果に統計的な差が検出されました（p < 0.05）**\n\n"
                       f"実測の初回達成率（`{real_first_rate:.2f}%`）と理論確率（`{theo_first_rate:.2f}%`）のギャップは誤差を超えています。")

        with st.expander("ℹ️ この検定（初回達成率）の計算式と仕組み"):
            st.write(f"""
            - **理論確率（初回達成率）の計算式**: 
              $$P(\\text{{初回で当選}}) = 1 - (1 - p)^N = 1 - \\left(1 - \\frac{{{bunsi[focused_item-1]}}}{{{bunbo}}}\\right)^{{{kaisu}}} \\approx {p_at_least_1_theo:.4f} \\quad (\\text{{約 }}{theo_first_rate:.2f}\\%)$$
            - **全 {kai} 回の実験での実測値**:
              - 最初の {kaisu} 回以内で当選達成: **{first_try_success} 回**（実測割合: **{real_first_rate:.2f}%**）
              - 最初の {kaisu} 回でハズレ: **{first_try_fail} 回**
            - **帰無仮説 ($H_0$)**: シミュレーションで「初めて当たる確率」は余事象の理論式 $1-(1-p)^N$ と一致する。
            """)

        st.divider()
        st.subheader(f"📈 [{focused_item}番目] の当選回数のバラつき（二項分布の可視化）")
        freq_fixed = pd.Series(focused_results).value_counts().sort_index()
        st.bar_chart(freq_fixed, color="#00a0ff", height=350)
        
        st.divider()
        with st.expander("📝 全アイテムのトータル当選データ一覧 ＆ カイ二乗検定を見る"):
            df_res = pd.DataFrame(fixed_mode_counts, columns=[f"{i+1}番目" for i in range(syurui)])
            df_summary = pd.DataFrame({
                "アイテムの種類": df_res.columns,
                "設定確率（分子）": bunsi,
                "トータル合計当選数 (回)": df_res.sum(),
                "1試行あたりの平均当選数 (回)": df_res.mean().round(2),
                "下振れ (最小当選数)": df_res.min(),
                "上振れ (最大当選数)": df_res.max()
            })
            st.dataframe(df_summary, hide_index=True, use_container_width=True)
            
            observed = df_res.sum().tolist()
            total_all_draws = kaisu * kai
            expected = [total_all_draws * (b / bunbo) for b in bunsi]
            
            chi2_stat, p_value = chisquare(f_obs=observed, f_exp=expected)
            
            st.markdown("---")
            st.subheader("🧪 全アイテムの排出比率に関するカイ二乗適合度検定")
            col_c1, col_c2, col_c3 = st.columns(3)
            col_c1.metric("カイ二乗統計量 ($\chi^2$)", f"{chi2_stat:.4f}")
            col_c2.metric("p値", f"{p_value:.4e}" if p_value < 0.0001 else f"{p_value:.4f}")
            
            if p_value < 0.05:
                col_c3.metric("判定 (有意水準 5%)", "有意な偏りあり ⚠️")
            else:
                col_c3.metric("判定 (有意水準 5%)", "有意差なし（正常） ✅")

            st.subheader("📈 各アイテムのトータル当選回数の比較")
            st.bar_chart(df_summary.set_index("アイテムの種類")["トータル合計当選数 (回)"], color="#00a0ff", height=350)

    final_log_text = "\n".join(log_lines)
    
    st.divider()
    st.subheader("💾 データのテキスト保存・管理")
    st.download_button(
        label="📥 詳細ログ（Textファイル）をダウンロード",
        data=final_log_text,
        file_name=f"gacha_sim_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain"
    )