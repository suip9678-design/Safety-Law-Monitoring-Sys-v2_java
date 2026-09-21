// 헤더의 "연동 확인 필요" 배지 + 팝업.
//
// 국가법령정보센터/KOSHA 가이드 Open API, 안전보건 뉴스 피드 3종처럼 이
// 앱이 의존하는 외부 연동이 계속 늘어나는데, 이 전부를 "데모 모드" 배지
// 하나로 뭉뚱그리면 정작 무엇이 문제인지 알 수 없다. 이 모듈은 항목별로
// 설정 여부/정상 동작 여부를 확인해서 문제가 있는 항목만 배지 카운트에
// 반영하고, 팝업에서 그 자리에 바로 값을 입력해 고칠 수 있게 한다.
//
// demo-mode.js가 다루는 "#demoBadge"(백엔드 자체가 없는 완전 오프라인
// 데모 여부)와는 별개의 개념이다 - 이 모듈은 백엔드는 정상 동작 중이되
// 그 안의 특정 외부 연동 하나가 설정이 안 됐거나 안 먹히는 경우를 다룬다.

import { api, toast } from "./core.js";

let lastStatus = null;

function computeIssueCount(s) {
  let count = 0;
  if (!s.law_api_oc_set) count++;
  if (!s.kosha_guide_api_key_set) count++;
  if (s.news_moel_showing_demo === true) count++;
  if (s.news_kosha_showing_demo === true) count++;
  if (s.news_accident_showing_demo === true) count++;
  return count;
}

function newsStatusLabel(showingDemo) {
  if (showingDemo === true) return "예시 데이터로 대체됨 - 이 URL을 확인하세요";
  if (showingDemo === false) return "정상 수집 중";
  return "아직 수집된 적 없음";
}

function renderModalFromStatus(s) {
  document.getElementById("intLawApiOc").value = s.law_api_oc || "";
  document.getElementById("intStatusLawApi").textContent = s.law_api_oc_set
    ? "설정됨 - 실제 법령 데이터로 동작 중"
    : "미설정 - 데모(예시) 데이터로 동작 중";

  document.getElementById("intKoshaApiKey").value = s.kosha_guide_api_key || "";
  document.getElementById("intKoshaApiUrl").value = s.kosha_guide_api_url || "";
  document.getElementById("intStatusKoshaApi").textContent = s.kosha_guide_api_key_set
    ? "설정됨"
    : "미설정 - KOSHA 가이드 탭의 \"API로 동기화\"를 쓸 수 없습니다";

  document.getElementById("intNewsMoelUrl").value = s.news_source_moel_url || "";
  document.getElementById("intStatusNewsMoel").textContent = newsStatusLabel(s.news_moel_showing_demo);

  document.getElementById("intNewsKoshaUrl").value = s.news_source_kosha_url || "";
  document.getElementById("intStatusNewsKosha").textContent = newsStatusLabel(s.news_kosha_showing_demo);

  document.getElementById("intNewsAccidentUrl").value = s.news_source_accident_url || "";
  document.getElementById("intStatusNewsAccident").textContent = newsStatusLabel(s.news_accident_showing_demo);
}

function updateBadge(issueCount) {
  const btn = document.getElementById("integrationAlertBtn");
  btn.hidden = issueCount === 0;
  btn.textContent = `⚠ 연동 확인 필요 (${issueCount})`;
}

export async function loadIntegrationStatus() {
  try {
    const s = await api("/api/settings");
    lastStatus = s;
    updateBadge(computeIssueCount(s));
    if (!document.getElementById("integrationStatusModalOverlay").hidden) {
      renderModalFromStatus(s);
    }
  } catch (e) {
    // 이 배지는 부가 기능이라, 조회 실패는 조용히 무시하고 화면 전체를 막지 않는다.
  }
}

function openIntegrationStatusModal() {
  if (lastStatus) renderModalFromStatus(lastStatus);
  document.getElementById("integrationStatusModalOverlay").hidden = false;
}

function closeIntegrationStatusModal() {
  document.getElementById("integrationStatusModalOverlay").hidden = true;
}

async function saveIntegrationField(key) {
  const payload = {};
  if (key === "law_api_oc") {
    payload.law_api_oc = document.getElementById("intLawApiOc").value;
  } else if (key === "kosha_guide_api") {
    payload.kosha_guide_api_key = document.getElementById("intKoshaApiKey").value;
    payload.kosha_guide_api_url = document.getElementById("intKoshaApiUrl").value;
  } else if (key === "news_source_moel_url") {
    payload.news_source_moel_url = document.getElementById("intNewsMoelUrl").value;
  } else if (key === "news_source_kosha_url") {
    payload.news_source_kosha_url = document.getElementById("intNewsKoshaUrl").value;
  } else if (key === "news_source_accident_url") {
    payload.news_source_accident_url = document.getElementById("intNewsAccidentUrl").value;
  }
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
    toast("저장했습니다.");
    await loadIntegrationStatus();
  } catch (e) {
    toast(`저장 실패: ${e.message}`, true);
  }
}

export function initIntegrationStatusModal() {
  document.getElementById("integrationAlertBtn").addEventListener("click", openIntegrationStatusModal);
  document.getElementById("integrationStatusCloseBtn").addEventListener("click", closeIntegrationStatusModal);
  document.getElementById("integrationStatusModalOverlay").addEventListener("click", (ev) => {
    if (ev.target.id === "integrationStatusModalOverlay") closeIntegrationStatusModal();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !document.getElementById("integrationStatusModalOverlay").hidden) closeIntegrationStatusModal();
  });
  document.querySelectorAll("[data-save-integration]").forEach((btn) => {
    btn.addEventListener("click", () => saveIntegrationField(btn.dataset.saveIntegration));
  });
}
