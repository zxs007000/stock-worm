# XGBoost 模型 SHAP 解释性分析（修正版）

- 数据: 真实 v4 原型 折1 落盘 (`/workspace/quant_proto/v4proto_out`), WFA 1 折 OOS 子样本(各 <=3000 行)
- 尺度说明: SHAP 值为 **log-odds(边际)** 贡献, 非概率; 标签为『未来收益排前30%的概率』(**排序/相对**, 非绝对收益方向)。
- base value(正类, log-odds) 各折: 1:-0.841

## 一、特征族总贡献 (Mean|SHAP| 归族, 缓和共线导致的信用瓜分)

- `ix_*`: 0.1171
- `crowd_liq*`: 0.0627
- `crowd_mom*`: 0.0142
- `mkt_*`: 0.0088
- `pca_absorp*`: 0.0082
- `netprofit*`: 0.0061
- `eps*`: 0.0038
- `ocf*`: 0.0035
- `chip_*`: 0.0029
- `debt*`: 0.0024
- `ret_*`: 0.0014
- `net_*`: 0.0012
- `amt_*`: 0.0012
- `rsi*`: 0.0008
- `ma_dev*`: 0.0006

## 二、Top 单特征 Mean|SHAP| (log-odds 尺度)

- `crowd_liq_pct`: 0.0534
- `crowd_mom`: 0.0067
- `crowd_liq`: 0.0062
- `netprofit_yoy`: 0.0061
- `pca_absorp`: 0.0053
- `crowd_mom_pct`: 0.0052
- `ix_mkt_ret20_std__chip_pr`: 0.0043
- `ix_mkt_gm_mean__ret_60`: 0.0040
- `ix_mkt_gm_mean__eps`: 0.0038
- `eps`: 0.0038
- `ix_mkt_ret20_std__ocf_netprofit`: 0.0036
- `ix_mkt_ret20_std__vol_20`: 0.0036
- `ocf_netprofit`: 0.0035
- `ix_mkt_amp_mean__eps`: 0.0033
- `mkt_vol_mean`: 0.0031
- `crowd_liq_roc`: 0.0029
- `ix_mkt_ma_dev_mean__amp_20`: 0.0024
- `debt_ratio`: 0.0024
- `ix_mkt_amt_chg_mean__ret_60`: 0.0022
- `crowd_mom_roc`: 0.0022
- `pca_absorp_pct`: 0.0021
- `ix_mkt_amp_mean__ret_20`: 0.0020
- `ix_mkt_vol_mean__netprofit_yoy`: 0.0018
- `ix_mkt_ret20_std__net_margin`: 0.0018
- `ix_mkt_amp_mean__net_margin`: 0.0018

## 三、跨折方向一致性 (稳健性, 非均值)

> 判定: 某因子在多数折中 median(SHAP) 同号 => 方向稳定; flip_folds 多 => 疑似伪Alpha(应剔除)。

| 因子 | 稳定方向 | 正向折 | 负向折 | 翻转折 | Mean|SHAP| |
|---|---|---|---|---|---|
| `crowd_liq_pct` | 正向 | 1 | 0 | 0 | 0.0534 |
| `crowd_mom` | 正向 | 1 | 0 | 0 | 0.0067 |
| `crowd_liq` | 负向 | 0 | 1 | 0 | 0.0062 |
| `netprofit_yoy` | 负向 | 0 | 1 | 0 | 0.0061 |
| `pca_absorp` | 负向 | 0 | 1 | 0 | 0.0053 |
| `crowd_mom_pct` | 正向 | 1 | 0 | 0 | 0.0052 |
| `ix_mkt_ret20_std__chip_pr` | 正向 | 1 | 0 | 0 | 0.0043 |
| `ix_mkt_gm_mean__ret_60` | 负向 | 0 | 1 | 0 | 0.0040 |
| `ix_mkt_gm_mean__eps` | 负向 | 0 | 1 | 0 | 0.0038 |
| `eps` | 正向 | 1 | 0 | 0 | 0.0038 |
| `ix_mkt_ret20_std__ocf_netprofit` | 正向 | 1 | 0 | 0 | 0.0036 |
| `ix_mkt_ret20_std__vol_20` | 负向 | 0 | 1 | 0 | 0.0036 |
| `ocf_netprofit` | 负向 | 0 | 1 | 0 | 0.0035 |
| `ix_mkt_amp_mean__eps` | 正向 | 1 | 0 | 0 | 0.0033 |
| `mkt_vol_mean` | 负向 | 0 | 1 | 0 | 0.0031 |
| `crowd_liq_roc` | 负向 | 0 | 1 | 0 | 0.0029 |
| `ix_mkt_ma_dev_mean__amp_20` | 正向 | 1 | 0 | 0 | 0.0024 |
| `debt_ratio` | 负向 | 0 | 1 | 0 | 0.0024 |
| `ix_mkt_amt_chg_mean__ret_60` | 负向 | 0 | 1 | 0 | 0.0022 |
| `crowd_mom_roc` | 负向 | 0 | 1 | 0 | 0.0022 |
| `pca_absorp_pct` | 负向 | 0 | 1 | 0 | 0.0021 |
| `ix_mkt_amp_mean__ret_20` | 正向 | 1 | 0 | 0 | 0.0020 |
| `ix_mkt_vol_mean__netprofit_yoy` | 负向 | 0 | 1 | 0 | 0.0018 |
| `ix_mkt_ret20_std__net_margin` | 正向 | 1 | 0 | 0 | 0.0018 |
| `ix_mkt_amp_mean__net_margin` | 正向 | 1 | 0 | 0 | 0.0018 |

## 四、关键因子依赖图(带 bootstrap CI)

- `pca_absorp_pen`: 依赖图见 shap_dep_pca_absorp_pen.png（含跨折 bootstrap CI）
- `ix_mkt_gm_mean__chip_cb`: 依赖图见 shap_dep_ix_mkt_gm_mean__chip_cb.png（含跨折 bootstrap CI）
- `crowd_mom_pct`: 依赖图见 shap_dep_crowd_mom_pct.png（含跨折 bootstrap CI）
- `pca_absorp_x_macro`: 依赖图见 shap_dep_pca_absorp_x_macro.png（含跨折 bootstrap CI）

## 五、交互解耦 (shap_interaction_values)

末折交互贡献 Top8 (|SHAP interaction| 合计, 已剔除自交互):
  - `crowd_liq_pct`: 40.2690
  - `ix_mkt_ma_dev_mean__amp_20`: 20.4235
  - `crowd_liq`: 19.6297
  - `crowd_liq_roc`: 18.8218
  - `ix_mkt_gm_mean__vol_20`: 17.5064
  - `vol_20`: 15.8552
  - `ix_mkt_ret20_std__ret_60`: 15.2713
  - `ix_mkt_ret20_std__eps`: 14.6412

## 六、结论与警示

- SHAP 仅解释**模型逻辑**, 不等同真值; 须与 OOS 的 AUC/IC 一并看。
- 同源特征族(pca_absorp_*/crowd_mom_*) 的 Mean|SHAP| 已归族汇总, 单特征方向可能被共线稀释, 解读单特征时谨慎。
- 依赖图尾部(>0.8/0.9 分位)样本稀疏, '断崖'多为噪声, **不得直接作为硬性止损线**; 阈值须带 CI 并经样本外验证。
- 标签为排序概率, SHAP 推高的是『进入前30%收益组』的概率, 不是绝对涨跌, 交易解读勿混淆。