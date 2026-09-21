// 상단 탭 전환 + 탭별로 어떤 로드 함수를 불러야 하는지 연결하는 라우터.
// 화면 전환 자체를 담당하므로 거의 모든 화면 모듈의 load*()를 가져온다.

import { state } from "./core.js";
import { loadDashboard } from "./dashboard.js";
import { loadNewsPage } from "./news-page.js";
import { loadLaws } from "./laws.js";
import { loadRevisions } from "./revisions.js";
import { loadKoshaGuides } from "./kosha-guide.js";
import { loadDocuments } from "./documents.js";
import { loadDocRevisions } from "./doc-revisions.js";
import { loadSettings } from "./settings.js";

export function activateTab(tab) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
}

export function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      activateTab(btn.dataset.tab);
      if (btn.dataset.tab === "revisions") state.revisionsLawFilter = null;
      loadTab(btn.dataset.tab);
    });
  });
}

export function viewRevisionsForLaw(lawId, lawName) {
  state.revisionsLawFilter = { id: lawId, name: lawName };
  activateTab("revisions");
  loadRevisions();
}

export function loadTab(tab) {
  if (tab === "dashboard") loadDashboard();
  if (tab === "news") loadNewsPage();
  if (tab === "laws") loadLaws();
  if (tab === "revisions") loadRevisions();
  if (tab === "kosha-guides") loadKoshaGuides();
  if (tab === "documents") loadDocuments();
  if (tab === "doc-revisions") loadDocRevisions();
  if (tab === "settings") loadSettings();
}
