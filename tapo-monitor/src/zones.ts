export interface Zone {
  id: number;
  name: string;
}

/** 대시보드에 표시할 9개 구역. 필요 시 실제 센서 매핑에 맞춰 이름을 바꾸면 됩니다. */
export const ZONES: readonly Zone[] = [
  { id: 1, name: "구역 1" },
  { id: 2, name: "구역 2" },
  { id: 3, name: "구역 3" },
  { id: 4, name: "구역 4" },
  { id: 5, name: "구역 5" },
  { id: 6, name: "구역 6" },
  { id: 7, name: "구역 7" },
  { id: 8, name: "구역 8" },
  { id: 9, name: "구역 9" },
] as const;
