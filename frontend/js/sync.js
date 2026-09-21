// 상단 "새로고침" 버튼 - 법령/고시 재검색 + 본문 캐시 갱신 + 신규 고시
// 탐지를 한 번에 실행하는 /api/sync 호출.

import { api, toast } from "./core.js";
import { loadDashboard } from "./dashboard.js";
import { loadTab } from "./tabs.js";

// 새로고침(동기화) 실행 - 상단 "새로고침" 버튼과 "신규 제정 고시 자동
// 탐지" 설정 저장 둘 다 여기를 거친다. 버튼 로딩 상태 표시가 필요할 때만
// btn을 넘기면 된다(설정 폼 저장은 자체적으로 다른 문구를 보여주므로
// 넘기지 않음).
export async function runSync(btn) {
  if (btn) {
    btn.disabled = true;
    btn.textContent = "새로고침 중...";
  }
  try {
    const result = await api("/api/sync", { method: "POST" });
    let msg = `동기화 완료: ${result.checked}건 확인, 신규 개정 ${result.new_revisions}건, 신규 고시 후보 ${result.new_admrul_candidates}건`;
    if (result.errors.length) msg += ` (오류 ${result.errors.length}건)`;
    toast(msg, result.errors.length > 0);
    loadDashboard();
    const activeTab = document.querySelector(".tab-btn.active").dataset.tab;
    loadTab(activeTab);
  } catch (e) {
    toast(`동기화 실패: ${e.message}`, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "새로고침";
    }
  }
}

export function initSyncButton() {
  document.getElementById("syncNowBtn").addEventListener("click", () => {
    runSync(document.getElementById("syncNowBtn"));
  });
}
