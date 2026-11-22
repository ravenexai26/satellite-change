export type State = "running" | "done" | "failed" | "stopped" | "interrupted" | "unknown";
export interface Status { stage?: string; state: State; message?: string; updated?: string }
export interface PeriodCfg { start: string; end: string; label?: string }
export interface Metrics {
  area_ha: { water_to_land: number; land_to_water: number };
  polygons: { total: number; high: number; medium: number; low: number; water_to_land: number; land_to_water: number };
  n_before: number; n_after: number; orbit: string;
}
export interface RunSummary {
  id: string; name: string; created?: string; source: "cdse" | "synthetic" | "local"; simulated: boolean;
  stage_requested: "search" | "all"; kind: "seasonal" | "quick"; bbox: [number, number, number, number];
  periods: { before: PeriodCfg; after: PeriodCfg }; status: Status; metrics: Metrics | null;
}
export interface FullMetrics extends Metrics {
  run_at: string; model_version: string; satellites: string[]; simulated: boolean; mode?: "multi_scene" | "single_pair";
  thresholds_db: { min: number; max: number; all_in_expected_range: boolean };
  calibration_check: { status: string; pixels?: number; median_before_db?: number; median_after_db?: number; difference_db?: number; limit_db?: number };
  validation?: Validation;
}
export interface Validation {
  optical_auto?: { polygons_checked: number; polygons_agree: number; polygon_agreement_rate: number | null; nochange_checked: number; nochange_agree: number; method: string };
  manual?: Record<"change" | "no_change", { samples: number; judged: number; correct: number; accuracy: number | null; unclear: number; unlabelled: number }>;
}
export interface RunDetail extends RunSummary { config: any; full_metrics: FullMetrics | null }
export interface AuditEntry { at: string; actor: string; action: string; note?: string }
export interface Alert {
  alert_id: string; source: string; type: "water_to_land" | "land_to_water"; geometry: GeoJSON.Geometry;
  observed_at: string; confidence: number; confidence_method: string; priority: "high" | "medium" | "low";
  area_ha: number; description: string; status: string; requires_human_verification: boolean;
  evidence: { before_scenes: string[]; after_scenes: string[]; image_chip: string | null };
  model_version: string; audit: AuditEntry[];
}
export interface Scene { period: string; date: string; satellite: string; orbit_direction: string; relative_orbit: string; aoi_coverage: string; scene_ids: string; selected: string }
export interface Threshold { date: string; period: string; satellite: string; threshold_db: string; method: string; tiles_used: string; water_share: string; in_expected_range: string }
export interface VRow { sample_id: string; kind: string; expected: string; lon: string; lat: string; auto_optical_agreement: string; label: string; notes: string }
export interface Defaults {
  bbox: [number, number, number, number]; periods: { before: PeriodCfg; after: PeriodCfg };
  change: { min_area_ha: number; water_before_min: number; water_after_max: number };
  min_per_period: number; credit: string; places: { name: string; lon: number; lat: number }[]; has_env_credentials: boolean;
  max_quick_km2: number;
}
export interface Acquisition { date: string; satellite: string; orbit?: string; cloud?: number | null }
