// "개정 이력" 탭: 법령/고시 개정 감지 이력 전체 목록, 상태 일괄 변경/삭제.

import { state, api, toast, fmtDate, fmtDateTime, escapeHtml, statusSelect, lawReasonDocUrl } from "./core.js";
import { wireStatusSelects } from "./status-actions.js";
import { loadDashboard } from "./dashboard.js";

// mode: "full"(개정 이력 탭) | "quick"(대시보드 "법령 개정 리스트")
// 상태 변경 드롭다운(statusSelect)은 두 모드 다 동일하게 사용한다 -
// 대시보드에서 바로 상태를 바꿔도 개정 이력 탭과 똑같이 동작해야 하고,
// 반영완료/해당없음으로 바뀐 건 대시보드 목록에서 빠져야 하기 때문.
// 개정 이력 탭(full)에서 체크된 개정 이력 id들 - 여러 건을 한 번에 상태
// 변경하기 위한 선택 상태. 목록을 새로 불러올 때마다 초기화됨.
let selectedRevisionIds = new Set();

export function renderRevisionsList(revisions, mode = "full") {
  const showFullActions = mode === "full";
  // "사규" 열은 개정 이력 탭(full)에서만 보여준다 - 대시보드(quick)에는
  // 문서 기준으로 재구성한 별도 섹션("사내 절차서·지침서 개정 필요 사항")이
  // 있어 여기서 또 보여주면 중복이라 뺐다.
  const showMappedDocs = showFullActions;
  const showCheckbox = showFullActions;
  return `
    <table>
      <thead><tr>
        ${showCheckbox ? `<th><input type="checkbox" id="revisionsSelectAllCheckbox" title="전체 선택"></th>` : ""}
        <th>법령/고시</th><th>구분</th><th>공포일자</th><th>시행일자</th><th>감지 시각</th>${showMappedDocs ? "<th>사규</th>" : ""}<th>상태</th>
      </tr></thead>
      <tbody>
        ${revisions.map((r) => {
          // 이전 값이 전혀 없으면(previous_*가 모두 비어있으면) 실제 개정이 아니라
          // 법령을 처음 등록할 때 자동 생성된 "최초 확인" 항목임.
          const isInitial = !r.previous_promulgation_date && !r.previous_enforcement_date;
          const reasonUrl = lawReasonDocUrl({
            source_type: r.tracked_law_source_type,
            external_id: r.tracked_law_external_id,
            enforcement_date: r.enforcement_date,
          });
          const nameCell = r.tracked_law_detail_link
            ? `<a href="${escapeHtml(r.tracked_law_detail_link)}" target="_blank" rel="noopener">${escapeHtml(r.tracked_law_name)}</a>`
            : escapeHtml(r.tracked_law_name);
          const promCell = reasonUrl
            ? `<a href="${escapeHtml(reasonUrl)}" target="_blank" rel="noopener" title="법령정보센터: 제정·개정이유 보기">${fmtDate(r.promulgation_date)}</a>`
            : fmtDate(r.promulgation_date);
          return `
          <tr>
            ${showCheckbox ? `<td><input type="checkbox" class="revision-row-checkbox" data-revision-id="${r.id}" ${selectedRevisionIds.has(r.id) ? "checked" : ""}></td>` : ""}
            <td>${nameCell}${isInitial ? ` <span class="hint">(신규 등록)</span>` : ""}</td>
            <td>${escapeHtml(r.tracked_law_category || "-")}</td>
            <td>${promCell}${r.previous_promulgation_date && r.previous_promulgation_date !== r.promulgation_date ? `<br><span class="hint">이전: ${fmtDate(r.previous_promulgation_date)}</span>` : ""}</td>
            <td>${fmtDate(r.enforcement_date)}</td>
            <td>${fmtDateTime(r.detected_at)}</td>
            ${showMappedDocs ? `<td>${r.mapped_documents.length ? r.mapped_documents.map(escapeHtml).join(", ") : '<span class="hint">해당 없음</span>'}</td>` : ""}
            <td>${statusSelect(r.id, r.review_status)}</td>
          </tr>
        `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderRevisionLawFilterChip() {
  const chip = document.getElementById("revisionLawFilterChip");
  if (!state.revisionsLawFilter) {
    chip.hidden = true;
    chip.innerHTML = "";
    return;
  }
  chip.hidden = false;
  chip.innerHTML = `법령 필터: <strong>${escapeHtml(state.revisionsLawFilter.name)}</strong> · <button class="link-btn" id="clearLawFilterBtn">전체 보기</button>`;
  document.getElementById("clearLawFilterBtn").addEventListener("click", () => {
    state.revisionsLawFilter = null;
    loadRevisions();
  });
}

function updateRevisionsBulkToolbar() {
  document.getElementById("revisionsSelectedCount").textContent = `${selectedRevisionIds.size}건 선택됨`;
  document.getElementById("revisionsBulkApplyBtn").disabled = selectedRevisionIds.size === 0;
  document.getElementById("revisionsBulkDeleteBtn").disabled = selectedRevisionIds.size === 0;
  const selectAll = document.getElementById("revisionsSelectAllCheckbox");
  if (selectAll) {
    const rowCheckboxes = document.querySelectorAll(".revision-row-checkbox");
    const checkedCount = document.querySelectorAll(".revision-row-checkbox:checked").length;
    selectAll.checked = rowCheckboxes.length > 0 && checkedCount === rowCheckboxes.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < rowCheckboxes.length;
  }
}

// 서버에서 마지막으로 받아온 전체 목록(상태/법령 필터 적용됨) - 법령명
// 검색창은 이걸 다시 불러오지 않고 클라이언트에서만 걸러서 다시 그린다.
let lastLoadedRevisions = [];

export function renderRevisionsTable() {
  const el = document.getElementById("revisionsTable");
  const searchText = document.getElementById("revisionsSearchInput").value.trim();
  const revisions = searchText
    ? lastLoadedRevisions.filter((r) => r.tracked_law_name.includes(searchText))
    : lastLoadedRevisions;
  selectedRevisionIds = new Set();
  el.innerHTML = revisions.length
    ? renderRevisionsList(revisions, "full")
    : `<div class="empty">${searchText ? `"${escapeHtml(searchText)}"와(과) 일치하는 개정 이력이 없습니다.` : "개정 이력이 없습니다."}</div>`;
  wireStatusSelects(el);
  el.querySelectorAll(".revision-row-checkbox").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = Number(cb.dataset.revisionId);
      if (cb.checked) selectedRevisionIds.add(id);
      else selectedRevisionIds.delete(id);
      updateRevisionsBulkToolbar();
    });
  });
  const selectAll = document.getElementById("revisionsSelectAllCheckbox");
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      el.querySelectorAll(".revision-row-checkbox").forEach((cb) => {
        cb.checked = selectAll.checked;
        const id = Number(cb.dataset.revisionId);
        if (selectAll.checked) selectedRevisionIds.add(id);
        else selectedRevisionIds.delete(id);
      });
      updateRevisionsBulkToolbar();
    });
  }
  updateRevisionsBulkToolbar();
}

export async function loadRevisions() {
  const status = document.getElementById("revisionStatusFilter").value;
  renderRevisionLawFilterChip();
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (state.revisionsLawFilter) params.set("tracked_law_id", state.revisionsLawFilter.id);
  try {
    lastLoadedRevisions = await api(`/api/revisions${params.toString() ? `?${params.toString()}` : ""}`);
    renderRevisionsTable();
  } catch (e) {
    toast(`개정 이력 로드 실패: ${e.message}`, true);
  }
}

async function applyRevisionsBulkStatus() {
  if (selectedRevisionIds.size === 0) return;
  const status = document.getElementById("revisionsBulkStatus").value;
  const btn = document.getElementById("revisionsBulkApplyBtn");
  btn.disabled = true;
  try {
    await api("/api/revisions/bulk-status", {
      method: "PATCH",
      body: JSON.stringify({ ids: Array.from(selectedRevisionIds), review_status: status }),
    });
    toast(`${selectedRevisionIds.size}건을 "${status}"(으)로 변경했습니다.`);
    loadRevisions();
    loadDashboard();
  } catch (e) {
    toast(`일괄 변경 실패: ${e.message}`, true);
    btn.disabled = false;
  }
}

async function deleteRevisionsBulk() {
  if (selectedRevisionIds.size === 0) return;
  const count = selectedRevisionIds.size;
  if (!confirm(`선택한 개정 이력 ${count}건을 삭제할까요? 되돌릴 수 없습니다.`)) return;
  const btn = document.getElementById("revisionsBulkDeleteBtn");
  btn.disabled = true;
  try {
    await api("/api/revisions/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ ids: Array.from(selectedRevisionIds) }),
    });
    toast(`${count}건을 삭제했습니다.`);
    loadRevisions();
    loadDashboard();
  } catch (e) {
    toast(`삭제 실패: ${e.message}`, true);
    btn.disabled = false;
  }
}

export function initRevisionsTab() {
  document.getElementById("revisionStatusFilter").addEventListener("change", loadRevisions);
  document.getElementById("revisionsSearchInput").addEventListener("input", renderRevisionsTable);
  document.getElementById("revisionsBulkApplyBtn").addEventListener("click", applyRevisionsBulkStatus);
  document.getElementById("revisionsBulkDeleteBtn").addEventListener("click", deleteRevisionsBulk);
}
