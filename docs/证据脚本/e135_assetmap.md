# GUI 图标资产映射（实证）

## 1. 单位头像 `assets/surfaces/unit/<type>/`

- 类型目录总数：**629**
- 同时有 `sheet_L.png` + `sheet_R.png`：**629**
- 只有 L：0；只有 R：0；两者都没有：0
- 目录内出现过的 png 文件名分布：{'sheet_L.png': 628, 'sheet_R.png': 629, 'sheet_l.png': 1}

- `sheet_L.png` 尺寸分布（前 60 个类型）：{(293, 198): 12, (234, 242): 6, (294, 198): 10, (367, 231): 3, (346, 198): 5, (294, 233): 8, (293, 233): 2, (292, 198): 14}

样例类型名（前 12）：aus_inf_41, aus_inf_div_dlc6, aus_inf_dlc4, aus_inf_dlc6, aus_inf_dlc7, bel_cav_40, bel_cha_40, bel_inf_40, bra_inf_44, bul_s_arm_dlc9, bul_s_cav_dlc9, bul_s_inf_dlc9

## 2. 特种兵图标 `assets/surfaces/specialist/<type>/`

- 特种兵类型目录总数：**379**

| 文件 | 存在的类型数 | 缺失的类型数 | 用途 |
|---|---|---|---|
| `sheet_act.png` | 378 | 1 | 战斗条上的活跃兵小图标（24×30） |
| `sheet_sup.png` | 378 | 1 | 战斗条上的压制兵小图标（39×50） |
| `status_act.png` | 378 | 1 | 状态面板里的活跃兵（52×68） |
| `status_sup.png` | 378 | 1 | 状态面板里的压制兵（72×48） |
| `sheet_large.png` | 378 | 1 | 大图，单位详情页用（160×160） |
| `hq_action_icon.png` | 378 | 1 | 总部菜单行动图标 |
| `hq_menu_icon.png` | 378 | 1 | 总部菜单条目图标 |

尺寸抽样（前 30 个类型）：

- `sheet_act.png`：{(24, 30): 30}
- `sheet_sup.png`：{(24, 30): 30}
- `status_act.png`：{(39, 50): 30}
- `status_sup.png`：{(39, 50): 30}
- `sheet_large.png`：{(52, 68): 30}
- `hq_action_icon.png`：{(160, 160): 30}
- `hq_menu_icon.png`：{(72, 48): 30}

## 3. 战力阶梯 `assets/surfaces/steps/`

- `eq_armor.png` — 72×48
- `eq_cavalry.png` — 72×48
- `eq_mountain.png` — 72×48
- `eq_ski.png` — 72×48
- `eq_step.png` — 72×48
- `step.png` — 72×48
- `step_armor_1.png` — 72×48
- `step_armor_2.png` — 72×48
- `step_cavalry_1.png` — 72×48
- `step_mountain_1.png` — 72×48
- `step_ski_1.png` — 72×48

## 4. 战区资产 `assets/surfaces/theater/`

- 文件总数：**44**；归一化后的资产条目数：**11**

| 资产条目 | 变体数 | 变体文件名 |
|---|---|---|
| air_attack | 4 | air_attack_disabled.png, air_attack_down.png, air_attack_hover.png, air_attack_neutral.png |
| air_attack_axis | 4 | air_attack_axis_disabled.png, air_attack_axis_down.png, air_attack_axis_hover.png, air_attack_axis_neutral.png |
| air_attack_soviet | 4 | air_attack_soviet_disabled.png, air_attack_soviet_down.png, air_attack_soviet_hover.png, air_attack_soviet_neutral.png |
| air_supply | 4 | air_supply_disabled.png, air_supply_down.png, air_supply_hover.png, air_supply_neutral.png |
| flying_artillery | 4 | flying_artillery_disabled.png, flying_artillery_down.png, flying_artillery_hover.png, flying_artillery_neutral.png |
| long_range_recon | 4 | long_range_recon_disabled.png, long_range_recon_down.png, long_range_recon_hover.png, long_range_recon_neutral.png |
| naval_bombardment | 4 | naval_bombardment_disabled.png, naval_bombardment_down.png, naval_bombardment_hover.png, naval_bombardment_neutral.png |
| naval_bombardment_axis | 4 | naval_bombardment_axis_disabled.png, naval_bombardment_axis_down.png, naval_bombardment_axis_hover.png, naval_bombardment_axis_neutral.png |
| precision_bombing | 4 | precision_bombing_disabled.png, precision_bombing_down.png, precision_bombing_hover.png, precision_bombing_neutral.png |
| saturation_strike | 4 | saturation_strike_disabled.png, saturation_strike_down.png, saturation_strike_hover.png, saturation_strike_neutral.png |
| saturation_strike_axis | 4 | saturation_strike_axis_disabled.png, saturation_strike_axis_down.png, saturation_strike_axis_hover.png, saturation_strike_axis_neutral.png |

## 5. 状态图标 `assets/surfaces/status/`

- `attack_full.png`
- `attack_locked.png`
- `binos_0.png`
- `binos_1.png`
- `def_elastic_defense.png`
- `def_no_retreat.png`
- `def_oversupply.png`
- `def_rearguard.png`
- `def_supply_dump.png`
- `entr_1.png`
- `entr_2.png`
- `exp_0.png`
- `exp_2_allies.png`
- `exp_2_axis.png`
- `exp_2_soviet.png`
- `exp_3_allies.png`
- `exp_3_axis.png`
- `exp_3_soviet.png`
- `hq_flag_inner.png`
- `hq_flag_outer.png`
- `hq_icon.png`
- `hq_state_att_1.png`
- `hq_state_att_1_wait.png`
- `hq_state_att_2.png`
- `hq_state_att_2_wait.png`
- `hq_state_att_3.png`
- `hq_state_att_3_wait.png`
- `hq_state_mov_1.png`
- `hq_state_mov_1_wait.png`
- `hq_state_sup_1.png`
- `hq_state_sup_2.png`
- `hq_state_sup_3.png`
- `move_full.png`
- `move_part.png`
- `out_of_hq_range.png`
- `para_mask.png`
- `quick_odds_bg.png`
- `quick_odds_sup.png`
- `step_bg.png`
- `step_mask_act.png`
- `step_mask_sup.png`
- `stragglers_mask.png`
- `stragglers_x.png`
- `supply_0.png`
- `supply_1.png`
- `supply_2.png`
- `truck_shadow.png`
- `truck_shape.png`
- `unit_move_2.png`
- `unit_move_3.png`
- `unit_move_shadow.png`
- `unit_move_undo.png`
- `weak.png`
- `x_bg.png`
- `x_mask.png`

## 6. 通用图标 `assets/surfaces/icon/` —— 共 211 个

arrow_air_attack.png, arrow_flying_artillery.png, arrow_naval_bombardment.png, arrow_precision_bombing.png, arrow_saturation_strike.png, attack_assault_crossing.png, attack_assault_crossing_unavailable.png, attack_bg.png, attack_bg_unavailable.png, attack_naval_assault.png, attack_naval_assault_unavailable.png, attack_paradrop.png, attack_pindown.png, attack_pindown_unavailable.png, attack_set_piece_attack.png, attack_set_piece_attack_unavailable.png, attack_suppressive_fire.png, attack_suppressive_fire_unavailable.png, city_obj_activate_unit.png, city_obj_activate_unit_mask.png, city_obj_card.png, city_obj_card_mask.png, city_obj_delay_unit.png, city_obj_delay_unit_mask.png, city_obj_hq_upgrade.png, city_obj_hq_upgrade_mask.png, city_obj_intel.png, city_obj_intel_mask.png, city_obj_prestige.png, city_obj_prestige_mask.png, city_obj_specialist.png, city_obj_specialist_mask.png, city_obj_supply.png, city_obj_supply_mask.png, city_obj_surrender_nation.png, city_obj_surrender_nation_mask.png, city_obj_token_A.png, city_obj_token_A_mask.png, city_obj_token_B.png, city_obj_token_B_mask.png, city_obj_token_C.png, city_obj_token_C_mask.png, city_obj_token_D.png, city_obj_token_D_mask.png, city_obj_token_E.png, city_obj_token_E_mask.png, city_obj_token_F.png, city_obj_token_F_mask.png, city_obj_token_G.png, city_obj_token_G_mask.png, city_obj_token_H.png, city_obj_token_H_mask.png, city_obj_token_I.png, city_obj_token_I_mask.png, city_obj_token_J.png, city_obj_token_J_mask.png, city_obj_token_K.png, city_obj_token_K_mask.png, city_obj_token_L.png, city_obj_token_L_mask.png, city_obj_token_M.png, city_obj_token_M_mask.png, city_obj_token_N.png, city_obj_token_N_mask.png, city_obj_token_O.png, city_obj_token_O_mask.png, city_obj_token_P.png, city_obj_token_P_mask.png, city_obj_token_Q.png, city_obj_token_Q_mask.png, city_obj_token_R.png, city_obj_token_R_mask.png, city_obj_token_S.png, city_obj_token_S_mask.png, city_obj_token_T.png, city_obj_token_T_mask.png, city_obj_token_U.png, city_obj_token_U_mask.png, city_obj_token_V.png, city_obj_token_V_mask.png, city_obj_token_W.png, city_obj_token_W_mask.png, city_obj_token_X.png, city_obj_token_X_mask.png, city_obj_token_Y.png, city_obj_token_Y_mask.png, city_obj_token_Z.png, city_obj_token_Z_mask.png, city_objective_primary.png, city_supply_air.png, city_supply_port.png, city_supply_rail.png, city_supply_ship.png, city_supply_truck.png, edit_problem.png, hex_unit_free.png, hq_action_eq_armor_1.png, hq_action_eq_armor_2.png, hq_action_eq_cavalry_1.png, hq_action_eq_mountain_1.png, hq_action_eq_none.png, hq_action_eq_ski_1.png, hq_action_step.png, hq_supply_none_0.png, hq_supply_none_1.png, hq_supply_none_2.png, hq_supply_none_3.png, intel_marker_armor_mask.png, intel_marker_armor_shadow.png, intel_marker_infantry_mask.png, intel_marker_infantry_shadow.png, intel_marker_mechanized_mask.png, intel_marker_mechanized_shadow.png, intel_marker_weak.png, legend_ALP.png, legend_BOC.png, legend_bridge.png, legend_bridge_destroyed.png, legend_bridge_pontoon.png, legend_bridge_pontoon_in_construction.png, legend_CDES.png, legend_CTY.png, legend_DES.png, legend_DUN.png, legend_esc_ridge.png, legend_FOR.png, legend_fort_destroyed.png, legend_fort_intact.png, legend_FSWP.png, legend_HIL.png, legend_hub_deployable.png, legend_hub_distance.png, legend_hub_not_deployable.png, legend_impassable.png, legend_MTN.png, legend_river.png, legend_SAL.png, legend_SCTY.png, legend_supplied.png, legend_supplied_hqs.png, legend_supplied_not.png, legend_supplied_rail.png, legend_supplied_rail_allies.png, legend_supplied_rail_axis.png, legend_supplied_rail_neutral.png, legend_supplied_rail_soviet.png, legend_supplied_units.png, legend_supply_hub.png, legend_supply_hub_allies.png, legend_supply_hub_axis.png, legend_supply_hub_neutral.png, legend_supply_hub_out_of_supply.png, legend_supply_hub_soviet.png, legend_SWP.png, legend_TUN.png, legend_wadi.png, long_range_recon.png, long_range_recon_no.png, move_min_3.png, movement_legend_min_3.png, movement_legend_unit_free.png, movement_legend_zoc.png, naval_in_fow.png, pa_closable.png, pa_invalid.png, pa_valid.png, recon_in_force.png, saturation_danger.png, sidebar.png, stopwatch.png, supply_0.png, supply_1.png, supply_2.png, supply_deployable.png, supply_fill.png, supply_hub_out_of_supply.png, supply_hub_out_of_supply_selected.png, supply_non_deployable.png, supply_none.png, terrain_ALP.png, terrain_BOC.png, terrain_bridge.png, terrain_bridge_destroyed.png, terrain_bridge_pontoon.png, terrain_bridge_pontoon_in_construction.png, terrain_CDES.png, terrain_CTY.png, terrain_DES.png, terrain_DUN.png, terrain_FOR.png, terrain_fort_destroyed.png, terrain_fort_intact.png, terrain_FSWP.png, terrain_HIL.png, terrain_LFOR.png, terrain_MTN.png, terrain_SAL.png, terrain_SCTY.png, terrain_SWP.png, terrain_TUN.png, unit_out_of_hq_range.png, unit_supply_none_0.png, unit_supply_none_1.png, unit_supply_none_2.png, unit_supply_none_3.png, weather_legend_dry.png, weather_legend_mud.png, weather_legend_snow.png, weather_mud.png, weather_snow.png, zoc.png

## 7. 其它资源批次

- `cards/`：72 个 png
- `hq_insignia/`：79 个 png
- `buttons/`：104 个 png
- `ui/`：219 个 png
- `sheet/`：137 个 png
- `milestones/`：462 个 png
- `nationality/`：533 个 png
- `faction/`：60 个 png
