// "사규 개정 이력" 탭: 대시보드의 "사내 절차서·지침서 개정 필요 사항"과
// 같은 형식(document-impacts.js)을 쓰되, 대시보드는 미검토/검토중 + 최대
// 몇 건만 보여주는 반면 여기는 상태 필터/검색을 걸어 처리 완료된 것까지
// 포함한 전체 이력을 다 보여준다.

import { api, toast, escapeHtml } from "./core.js";
import { renderDocumentImpactsList } from "./document-impacts.js";
import { wireStatusSelects } from "./status-actions.js";

let lastLoadedDocRevisions = [];

export async function loadDocRevisions() {
  const status = document.getElementById("docRevisionStatusFilter").value;
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  try {
    lastLoadedDocRevisions = await api(`/api/documents/impacts${params.toString() ? `?${params.toString()}` : ""}`);
    renderDocRevisionsTable();
  } catch (e) {
    toast(`사규 개정 이력 로드 실패: ${e.message}`, true);
  }
}

export function renderDocRevisionsTable() {
  const el = document.getElementById("docRevisionsTable");
  const searchText = document.getElementById("docRevisionsSearchInput").value.trim();
  const docImpacts = searchText
    ? lastLoadedDocRevisions.filter((d) =>
        d.document_title.includes(searchText) || d.revisions.some((r) => r.tracked_law_name.includes(searchText))
      )
    : lastLoadedDocRevisions;
  el.innerHTML = docImpacts.length
    ? renderDocumentImpactsList(docImpacts)
    : `<div class="empty">${searchText ? `"${escapeHtml(searchText)}"와(과) 일치하는 사규 개정 이력이 없습니다.` : "사규와 매핑된 법령의 개정 이력이 없습니다. 사규 추가/수정 화면에서 근거 법령을 연결해보세요."}</div>`;
  wireStatusSelects(el);
}

export function initDocRevisionsTab() {
  document.getElementById("docRevisionStatusFilter").addEventListener("change", loadDocRevisions);
  document.getElementById("docRevisionsSearchInput").addEventListener("input", renderDocRevisionsTable);
}
