// "설정" 탭: 국가법령정보센터 OC 키, 신규 제정 고시 자동 탐지 조건,
// 무시한 고시 후보 관리, 법령 본문 캐시/전체 법령 자동 캐시, 안전보건
// 뉴스 게시판 설정, 자동 동기화 안내.

import { api, toast, fmtDateTime, escapeHtml } from "./core.js";
import { runSync } from "./sync.js";
import { loadNewsBoard } from "./news.js";
import { loadDashboard } from "./dashboard.js";
import { loadIntegrationStatus } from "./integration-status.js";

// ---------- 무시한 신규 고시 후보 관리 ----------

let dismissedAdmrulLoaded = false;
let lastLoadedDismissed = [];
let selectedDismissedIds = new Set();

function updateDismissedBulkToolbar() {
  document.getElementById("dismissedAdmrulSelectedCount").textContent = `${selectedDismissedIds.size}건 선택됨`;
  document.getElementById("dismissedAdmrulBulkRestoreBtn").disabled = selectedDismissedIds.size === 0;
  const selectAll = document.getElementById("dismissedAdmrulSelectAllCheckbox");
  if (selectAll) {
    const rowCheckboxes = document.querySelectorAll(".dismissed-row-checkbox");
    const checkedCount = document.querySelectorAll(".dismissed-row-checkbox:checked").length;
    selectAll.checked = rowCheckboxes.length > 0 && checkedCount === rowCheckboxes.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < rowCheckboxes.length;
  }
}

function renderDismissedAdmrulTable() {
  const el = document.getElementById("dismissedAdmrulTable");
  const searchText = document.getElementById("dismissedAdmrulSearchInput").value.trim();
  const candidates = searchText
    ? lastLoadedDismissed.filter((c) => (c.name || "").includes(searchText))
    : lastLoadedDismissed;
  selectedDismissedIds = new Set();
  el.hidden = false;
  document.getElementById("dismissedAdmrulControls").hidden = false;

  if (!candidates.length) {
    el.innerHTML = `<div class="empty">무시한 항목이 없습니다.</div>`;
    updateDismissedBulkToolbar();
    return;
  }

  el.innerHTML = `
    <table>
      <thead><tr>
        <th><input type="checkbox" id="dismissedAdmrulSelectAllCheckbox" title="전체 선택"></th>
        <th>법령/고시</th><th>구분</th><th>소관부처</th><th>공포일자</th><th>매칭 키워드</th><th></th>
      </tr></thead>
      <tbody>
        ${candidates.map((c) => `
          <tr>
            <td><input type="checkbox" class="dismissed-row-checkbox" data-dismissed-id="${c.id}" ${selectedDismissedIds.has(c.id) ? "checked" : ""}></td>
            <td>${c.detail_link
              ? `<a href="${escapeHtml(c.detail_link)}" target="_blank" rel="noopener">${escapeHtml(c.name)}</a>`
              : escapeHtml(c.name)}</td>
            <td>${escapeHtml(c.category || "-")}</td>
            <td>${escapeHtml(c.department || "-")}</td>
            <td>${(c.promulgation_date || "-").toString().replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")}</td>
            <td><span class="hint">${escapeHtml(c.matched_keyword || "-")}</span></td>
            <td><button class="btn" data-restore-candidate="${c.id}">복원</button></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  el.querySelectorAll("[data-restore-candidate]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "복원 중...";
      try {
        await api(`/api/laws/new-admrul-candidates/${btn.dataset.restoreCandidate}/restore`, { method: "POST" });
        toast("복원했습니다. 다음 새로고침부터 다시 후보 목록에 나타납니다.");
        loadDismissedAdmrulCandidates();
        loadDashboard();
      } catch (e) {
        toast(`복원 실패: ${e.message}`, true);
        btn.disabled = false;
        btn.textContent = "복원";
      }
    });
  });

  el.querySelectorAll(".dismissed-row-checkbox").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = Number(cb.dataset.dismissedId);
      if (cb.checked) selectedDismissedIds.add(id);
      else selectedDismissedIds.delete(id);
      updateDismissedBulkToolbar();
    });
  });

  const selectAll = document.getElementById("dismissedAdmrulSelectAllCheckbox");
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      el.querySelectorAll(".dismissed-row-checkbox").forEach((cb) => {
        cb.checked = selectAll.checked;
        const id = Number(cb.dataset.dismissedId);
        if (selectAll.checked) selectedDismissedIds.add(id);
        else selectedDismissedIds.delete(id);
      });
      updateDismissedBulkToolbar();
    });
  }

  updateDismissedBulkToolbar();
}

async function loadDismissedAdmrulCandidates() {
  try {
    lastLoadedDismissed = await api("/api/laws/new-admrul-candidates/dismissed");
    renderDismissedAdmrulTable();
  } catch (e) {
    toast(`무시한 항목 로드 실패: ${e.message}`, true);
  }
}

async function restoreDismissedBulk() {
  if (selectedDismissedIds.size === 0) return;
  const count = selectedDismissedIds.size;
  const btn = document.getElementById("dismissedAdmrulBulkRestoreBtn");
  btn.disabled = true;
  try {
    await api("/api/laws/new-admrul-candidates/bulk-restore", {
      method: "POST",
      body: JSON.stringify({ ids: Array.from(selectedDismissedIds) }),
    });
    toast(`${count}건을 복원했습니다. 다음 새로고침부터 다시 후보 목록에 나타납니다.`);
    loadDismissedAdmrulCandidates();
    loadDashboard();
  } catch (e) {
    toast(`일괄 복원 실패: ${e.message}`, true);
    btn.disabled = false;
  }
}

function initDismissedAdmrulPanel() {
  document.getElementById("loadDismissedBtn").addEventListener("click", () => {
    dismissedAdmrulLoaded = true;
    loadDismissedAdmrulCandidates();
  });
  document.getElementById("dismissedAdmrulSearchInput").addEventListener("input", renderDismissedAdmrulTable);
  document.getElementById("dismissedAdmrulBulkRestoreBtn").addEventListener("click", restoreDismissedBulk);
}

// ---------- 설정 폼 ----------

// 저장 형식(YYYYMMDD)과 <input type="date">가 쓰는 형식(YYYY-MM-DD) 사이 변환.
function yyyymmddToDateInput(v) {
  if (!v || v.length !== 8) return "";
  return `${v.slice(0, 4)}-${v.slice(4, 6)}-${v.slice(6, 8)}`;
}

function dateInputToYyyymmdd(v) {
  return v ? v.replaceAll("-", "") : "";
}

export async function loadSettings() {
  try {
    const s = await api("/api/settings");
    document.getElementById("settingOc").value = s.law_api_oc || "";
    document.getElementById("settingOc").placeholder = "OC 키";
    document.getElementById("ocStatus").textContent = s.demo_mode
      ? "OC 키가 설정되지 않아 데모 데이터로 동작 중입니다."
      : `현재 동기화된 OC 키: ${s.law_api_oc} (실제 국가법령정보센터 API로 동작 중)`;

    document.getElementById("koshaGuideApiKey").value = s.kosha_guide_api_key || "";
    document.getElementById("koshaGuideApiUrl").value = s.kosha_guide_api_url || "";
    document.getElementById("koshaGuideApiStatus").textContent = s.kosha_guide_api_key_set
      ? "인증키가 저장되어 있습니다. KOSHA 가이드 탭에서 \"API로 동기화\"를 눌러보세요."
      : "아직 인증키가 없습니다. 키를 저장하면 KOSHA 가이드 탭에서 자동 동기화를 쓸 수 있습니다.";

    document.getElementById("autoSyncHint").textContent = s.auto_sync_interval_hours > 0
      ? `서버가 실행 중인 동안 ${s.auto_sync_interval_hours}시간마다 자동으로 동기화합니다. (.env의 AUTO_SYNC_INTERVAL_HOURS)`
      : "자동 동기화가 꺼져 있습니다. (.env의 AUTO_SYNC_INTERVAL_HOURS=0)";

    document.getElementById("newAdmrulDepartment").value = s.new_admrul_department || "";
    document.getElementById("newAdmrulKeywords").value = s.new_admrul_keywords || "";
    document.getElementById("newAdmrulSinceDate").value = yyyymmddToDateInput(s.new_admrul_since_date);
    document.getElementById("fullLawCacheEnabled").checked = !!s.full_law_cache_enabled;

    document.getElementById("newsTickerEnabled").checked = !!s.news_ticker_enabled;
    document.getElementById("newsSourceMoelUrl").value = s.news_source_moel_url || "";
    document.getElementById("newsSourceKoshaUrl").value = s.news_source_kosha_url || "";
    document.getElementById("newsSourceAccidentUrl").value = s.news_source_accident_url || "";
    document.getElementById("newsRetentionDays").value = s.news_retention_days || 180;
  } catch (e) {
    toast(`설정 로드 실패: ${e.message}`, true);
  }
  loadContentCacheStatus();
  loadFullLawCacheStatus();
  if (dismissedAdmrulLoaded) loadDismissedAdmrulCandidates();
}

async function loadContentCacheStatus() {
  try {
    const status = await api("/api/content-cache/status");
    document.getElementById("contentCacheStatus").textContent =
      status.cached_count > 0
        ? `현재 ${status.cached_count}건 캐시됨 (마지막 갱신: ${fmtDateTime(status.last_cached_at)})`
        : "아직 캐시된 본문이 없습니다. 새로고침을 눌러 채워주세요.";
  } catch (e) {
    document.getElementById("contentCacheStatus").textContent = "";
  }
}

let fullLawCachePollTimer = null;

function renderFullLawCacheStatus(status) {
  const el = document.getElementById("fullLawCacheStatus");
  // processed(새로 받음) + skipped(공포번호 그대로라 건너뜀)를 합친 게
  // total(전체 목록 건수)에 가까워야 정상적으로 끝까지 돈 것이다.
  const handled = status.processed + status.skipped;
  const progress = status.total ? `${handled} / ${status.total}건` : `${handled}건`;
  const detail = `(새로 받음 ${status.processed}건, 변경 없어 건너뜀 ${status.skipped}건)`;
  if (status.running) {
    el.textContent = `진행 중... 지금까지 ${progress} 확인 ${detail}`;
  } else if (status.error) {
    el.textContent = `마지막 실행 중 오류 발생 (${progress}까지 확인 ${detail}): ${status.error}`;
  } else if (status.finished_at) {
    el.textContent = `마지막 완료: ${fmtDateTime(status.finished_at)} (총 ${progress} 확인 ${detail})`;
  } else {
    el.textContent = "아직 실행한 적 없습니다.";
  }
}

// 진행 중일 때만 몇 초 간격으로 상태를 다시 물어본다 - 서버가 백그라운드로
// 계속 도는 작업이라 완료될 때까지 화면에서 진행 상황을 보여주기 위함.
async function loadFullLawCacheStatus() {
  try {
    const status = await api("/api/content-cache/full-refresh-status");
    renderFullLawCacheStatus(status);
    if (status.running && !fullLawCachePollTimer) {
      fullLawCachePollTimer = setInterval(async () => {
        try {
          const s = await api("/api/content-cache/full-refresh-status");
          renderFullLawCacheStatus(s);
          if (!s.running) {
            clearInterval(fullLawCachePollTimer);
            fullLawCachePollTimer = null;
            loadContentCacheStatus();
          }
        } catch (_) { /* 다음 주기에 다시 시도 */ }
      }, 3000);
    }
  } catch (e) {
    document.getElementById("fullLawCacheStatus").textContent = "";
  }
}

export function initSettingsForms() {
  document.getElementById("saveOcBtn").addEventListener("click", async () => {
    const value = document.getElementById("settingOc").value;
    if (!value) { toast("OC 키를 입력하세요.", true); return; }
    try {
      await api("/api/settings", { method: "PUT", body: JSON.stringify({ law_api_oc: value }) });
      toast("OC 키를 저장했습니다.");
      loadSettings();
      loadIntegrationStatus();
    } catch (e) {
      toast(`저장 실패: ${e.message}`, true);
    }
  });

  document.getElementById("koshaGuideApiForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = {
      kosha_guide_api_key: document.getElementById("koshaGuideApiKey").value,
      kosha_guide_api_url: document.getElementById("koshaGuideApiUrl").value,
    };
    const btn = ev.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      toast("KOSHA 가이드 Open API 설정을 저장했습니다.");
      loadSettings();
      loadIntegrationStatus();
    } catch (e) {
      toast(`저장 실패: ${e.message}`, true);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("refreshContentCacheBtn").addEventListener("click", async () => {
    const btn = document.getElementById("refreshContentCacheBtn");
    btn.disabled = true;
    btn.textContent = "캐시 새로고침 중... (다소 시간이 걸릴 수 있습니다)";
    try {
      const result = await api("/api/content-cache/refresh", { method: "POST" });
      toast(`본문 캐시 새로고침 완료: 총 ${result.cached_count}건`);
      loadContentCacheStatus();
    } catch (e) {
      toast(`본문 캐시 새로고침 실패: ${e.message}`, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "본문 캐시 새로고침";
    }
  });

  document.getElementById("saveFullLawCacheBtn").addEventListener("click", async () => {
    try {
      await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ full_law_cache_enabled: document.getElementById("fullLawCacheEnabled").checked }),
      });
      toast("저장했습니다.");
    } catch (e) {
      toast(`저장 실패: ${e.message}`, true);
    }
  });

  document.getElementById("startFullLawCacheBtn").addEventListener("click", async () => {
    const btn = document.getElementById("startFullLawCacheBtn");
    btn.disabled = true;
    try {
      await api("/api/content-cache/full-refresh", { method: "POST" });
      toast("전체 법령 캐시를 백그라운드에서 시작했습니다. 완료까지 시간이 걸릴 수 있습니다.");
      loadFullLawCacheStatus();
    } catch (e) {
      toast(`시작 실패: ${e.message}`, true);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("newAdmrulForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = {
      new_admrul_department: document.getElementById("newAdmrulDepartment").value,
      new_admrul_keywords: document.getElementById("newAdmrulKeywords").value,
      new_admrul_since_date: dateInputToYyyymmdd(document.getElementById("newAdmrulSinceDate").value),
    };
    const btn = ev.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = "저장 중...";
    try {
      await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      await loadSettings();
      // 저장만 하고 끝나면 "설정을 바꿨는데 왜 목록이 그대로냐"는 오해가
      // 생기기 쉬워서(실제로 사용자가 그렇게 겪었다), 저장에 성공하면
      // 곧바로 새로고침(동기화)까지 이어서 실행한다.
      btn.textContent = "저장 후 새로고침 중...";
      await runSync();
    } catch (e) {
      toast(`저장 실패: ${e.message}`, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "저장";
    }
  });

  document.getElementById("newsSettingsForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = {
      news_ticker_enabled: document.getElementById("newsTickerEnabled").checked,
      news_source_moel_url: document.getElementById("newsSourceMoelUrl").value,
      news_source_kosha_url: document.getElementById("newsSourceKoshaUrl").value,
      news_source_accident_url: document.getElementById("newsSourceAccidentUrl").value,
      news_retention_days: Number(document.getElementById("newsRetentionDays").value) || 180,
    };
    const btn = ev.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
      document.getElementById("newsSettingsStatus").textContent = "저장했습니다.";
      loadNewsBoard();
      loadIntegrationStatus();
    } catch (e) {
      toast(`저장 실패: ${e.message}`, true);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("newsSyncNowBtn").addEventListener("click", async () => {
    const btn = document.getElementById("newsSyncNowBtn");
    btn.disabled = true;
    btn.textContent = "새로고침 중...";
    try {
      const result = await api("/api/news/sync", { method: "POST" });
      document.getElementById("newsSettingsStatus").textContent = `새로고침 완료: 신규 ${result.added}건`;
      loadNewsBoard();
      loadIntegrationStatus();
    } catch (e) {
      toast(`새로고침 실패: ${e.message}`, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "지금 새로고침";
    }
  });

  initDismissedAdmrulPanel();
}
