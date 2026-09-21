// 앱 진입점. 화면별 모듈들의 init*()/load*()를 불러와 DOMContentLoaded
// 시점에 한 번 배선하는 역할만 한다 - 실제 로직은 각 모듈 안에 있다.

import { initTabs, loadTab } from "./tabs.js";
import { initLawsTab } from "./laws.js";
import { initRevisionsTab } from "./revisions.js";
import { initKoshaGuideForm, initKoshaGuideSearch, initKoshaGuideSync, initKoshaGuideBulkImport, initKoshaGuideBulkDelete, initKoshaGuideContentCache } from "./kosha-guide.js";
import { initDocRevisionsTab } from "./doc-revisions.js";
import { initDocumentForm } from "./documents.js";
import { initSettingsForms } from "./settings.js";
import { initSyncButton } from "./sync.js";
import { initAlarmBell } from "./alarm.js";
import { initHelpModal } from "./help.js";
import { initKeywordSearch } from "./keyword-search.js";
import { initNewsBoard } from "./news.js";
import { initNewsPage } from "./news-page.js";
import { loadIntegrationStatus, initIntegrationStatusModal } from "./integration-status.js";
import { loadDashboard } from "./dashboard.js";

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initLawsTab();
  initRevisionsTab();
  initKoshaGuideForm();
  initKoshaGuideSearch();
  initKoshaGuideSync();
  initKoshaGuideBulkImport();
  initKoshaGuideBulkDelete();
  initKoshaGuideContentCache();
  initDocRevisionsTab();
  initDocumentForm();
  initSettingsForms();
  initSyncButton();
  initAlarmBell();
  initHelpModal();
  initKeywordSearch();
  initNewsBoard();
  initNewsPage();
  initIntegrationStatusModal();

  loadDashboard();
  loadIntegrationStatus();

  // 다른 브라우저 탭/창을 보다가 이 화면으로 돌아왔을 때 자동으로 최신
  // 내용을 다시 불러온다. 설정을 저장하면 자동으로 새로고침(동기화)까지
  // 되긴 하지만, 그건 저장한 그 브라우저 탭 안에서만 반영되고 다른 탭에
  // 이미 열어둔 화면(예: 대시보드를 한쪽 탭에 띄워두고 다른 탭에서 설정을
  // 바꾼 경우)에는 전달되지 않아, 결국 F5를 눌러야 하는 불편함이 있었다.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    const activeTab = document.querySelector(".tab-btn.active").dataset.tab;
    loadTab(activeTab);
    if (activeTab !== "dashboard") loadDashboard();
    loadIntegrationStatus();
  });
});
