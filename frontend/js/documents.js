// "사규" 탭: 회사 문서(절차서/지침서/작업표준) CRUD, 키워드(해시태그),
// 근거 법령 매핑 체크박스.

import { state, api, toast, fmtDate, escapeHtml } from "./core.js";
import { sortLaws, lawCategoryRank } from "./laws.js";
import { loadDashboard } from "./dashboard.js";

// 근거 법령 체크박스 목록은 구분 필터/검색어에 따라 계속 다시 그려지므로,
// 어떤 법령이 선택됐는지는 화면의 :checked 상태가 아니라 이 Set으로 따로
// 추적한다(필터링으로 화면에서 안 보이는 항목도 선택은 유지되어야 함).
let selectedDocLawIds = new Set();

export async function loadDocuments() {
  try {
    const [documents, laws] = await Promise.all([api("/api/documents"), api("/api/laws")]);
    state.documents = documents;
    state.laws = laws;
    renderDocumentsTable();
  } catch (e) {
    toast(`문서 목록 로드 실패: ${e.message}`, true);
  }
}

function renderDocLawCheckboxes() {
  const el = document.getElementById("docLawCheckboxes");
  if (!state.laws.length) {
    el.innerHTML = `<span class="hint">먼저 "법령 마스터" 탭에서 법령을 등록하세요.</span>`;
    return;
  }
  const categoryFilter = document.getElementById("docLawCategoryFilter").value;
  const searchText = document.getElementById("docLawSearchInput").value.trim();
  const filtered = sortLaws(state.laws).filter((l) => {
    if (categoryFilter !== "" && String(lawCategoryRank(l.category)) !== categoryFilter) return false;
    if (searchText && !l.name.includes(searchText)) return false;
    return true;
  });
  if (!filtered.length) {
    el.innerHTML = `<span class="hint">조건에 맞는 법령이 없습니다.</span>`;
    return;
  }
  el.innerHTML = filtered
    .map(
      (l) => `
    <label>
      <input type="checkbox" class="doc-law-checkbox" value="${l.id}" ${selectedDocLawIds.has(l.id) ? "checked" : ""}>
      ${escapeHtml(l.name)} <span class="hint">(${escapeHtml(l.category || "-")})</span>
    </label>
  `
    )
    .join("");
  el.querySelectorAll(".doc-law-checkbox").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = Number(cb.value);
      if (cb.checked) selectedDocLawIds.add(id);
      else selectedDocLawIds.delete(id);
    });
  });
}

// "#밀폐공간 #공기호흡기" 같은 입력을 저장용 CSV("밀폐공간,공기호흡기")로,
// 그 반대로도 변환한다. 공백/콤마 어느 쪽으로 구분해도 되고 "#"은 있어도
// 없어도 된다.
function normalizeTagsInput(raw) {
  return (raw || "")
    .split(/[\s,]+/)
    .map((t) => t.replace(/^#/, "").trim())
    .filter(Boolean)
    .join(",");
}

function formatTagsForInput(tagsCsv) {
  return (tagsCsv || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)
    .map((t) => `#${t}`)
    .join(" ");
}

function renderTagChips(tagsCsv) {
  const tags = (tagsCsv || "").split(",").map((t) => t.trim()).filter(Boolean);
  if (!tags.length) return '<span class="hint">없음</span>';
  return tags.map((t) => `<span class="tag-chip">#${escapeHtml(t)}</span>`).join(" ");
}

function openDocumentModal() {
  document.getElementById("documentModalOverlay").hidden = false;
}

function closeDocumentModal() {
  document.getElementById("documentModalOverlay").hidden = true;
}

function renderDocumentsTable() {
  const el = document.getElementById("documentsTable");
  if (!state.documents.length) {
    el.innerHTML = `<div class="empty">등록된 사규가 없습니다.</div>`;
    return;
  }
  el.innerHTML = `
    <table>
      <thead><tr><th>구분</th><th>문서번호</th><th>제목</th><th>개정번호</th><th>개정일자</th><th>담당자</th><th>키워드</th><th>근거 법령</th><th></th></tr></thead>
      <tbody>
        ${state.documents.map((d) => `
          <tr>
            <td>${escapeHtml(d.doc_type)}</td>
            <td>${escapeHtml(d.doc_number || "-")}</td>
            <td>${escapeHtml(d.title)}</td>
            <td>${escapeHtml(d.revision_no || "-")}</td>
            <td>${fmtDate(d.revision_date)}</td>
            <td>${escapeHtml(d.owner || "-")}</td>
            <td>${renderTagChips(d.tags)}</td>
            <td>${d.mapped_laws.length ? d.mapped_laws.map(escapeHtml).join(", ") : '<span class="hint">없음</span>'}</td>
            <td>
              <button class="link-btn" data-edit-doc="${d.id}">수정</button>
              <button class="link-btn" data-delete-doc="${d.id}">삭제</button>
            </td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  el.querySelectorAll("[data-edit-doc]").forEach((btn) => {
    btn.addEventListener("click", () => startEditDocument(Number(btn.dataset.editDoc)));
  });
  el.querySelectorAll("[data-delete-doc]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("이 문서를 삭제할까요? (관련 매핑도 함께 삭제됩니다)")) return;
      try {
        await api(`/api/documents/${btn.dataset.deleteDoc}`, { method: "DELETE" });
        toast("삭제했습니다.");
        loadDocuments();
      } catch (e) {
        toast(`삭제 실패: ${e.message}`, true);
      }
    });
  });
}

async function startEditDocument(id) {
  const d = state.documents.find((x) => x.id === id);
  if (!d) return;
  document.getElementById("documentFormTitle").textContent = "사규 수정";
  document.getElementById("docId").value = d.id;
  document.getElementById("docType").value = d.doc_type;
  document.getElementById("docNumber").value = d.doc_number || "";
  document.getElementById("docTitle").value = d.title;
  document.getElementById("docRevisionNo").value = d.revision_no || "";
  document.getElementById("docRevisionDate").value = d.revision_date || "";
  document.getElementById("docOwner").value = d.owner || "";
  document.getElementById("docFileLink").value = d.file_link || "";
  document.getElementById("docTags").value = formatTagsForInput(d.tags);
  document.getElementById("docNote").value = d.note || "";
  document.getElementById("docLawCategoryFilter").value = "";
  document.getElementById("docLawSearchInput").value = "";
  try {
    const mappings = await api(`/api/mappings?document_id=${id}`);
    selectedDocLawIds = new Set(mappings.map((m) => m.tracked_law_id));
    renderDocLawCheckboxes();
  } catch (e) {
    toast(`매핑된 법령 로드 실패: ${e.message}`, true);
  }
  openDocumentModal();
}

function resetDocumentForm() {
  document.getElementById("documentFormTitle").textContent = "사규 추가";
  document.getElementById("documentForm").reset();
  document.getElementById("docId").value = "";
  document.getElementById("docLawCategoryFilter").value = "";
  document.getElementById("docLawSearchInput").value = "";
  selectedDocLawIds = new Set();
  renderDocLawCheckboxes();
}

// 문서를 저장한 뒤, 체크박스로 고른 법령 목록과 실제 DB에 저장된 매핑을
// 비교해서 새로 추가된 건 등록하고 해제된 건 삭제한다.
async function syncDocumentLawMappings(documentId) {
  const selectedLawIds = Array.from(selectedDocLawIds);
  let existing = [];
  try {
    existing = await api(`/api/mappings?document_id=${documentId}`);
  } catch (e) {
    toast(`기존 매핑 조회 실패: ${e.message}`, true);
    return;
  }
  const existingLawIds = new Set(existing.map((m) => m.tracked_law_id));
  const toAdd = selectedLawIds.filter((lawId) => !existingLawIds.has(lawId));
  const toRemove = existing.filter((m) => !selectedLawIds.includes(m.tracked_law_id));

  const results = await Promise.allSettled([
    ...toAdd.map((lawId) =>
      api("/api/mappings", { method: "POST", body: JSON.stringify({ document_id: documentId, tracked_law_id: lawId }) })
    ),
    ...toRemove.map((m) => api(`/api/mappings/${m.id}`, { method: "DELETE" })),
  ]);
  const failed = results.filter((r) => r.status === "rejected");
  if (failed.length) {
    toast(`근거 법령 연결 중 일부 실패 (${failed.length}건)`, true);
  }
}

export function initDocumentForm() {
  document.getElementById("documentForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const id = document.getElementById("docId").value;
    const payload = {
      doc_type: document.getElementById("docType").value,
      doc_number: document.getElementById("docNumber").value || null,
      title: document.getElementById("docTitle").value,
      revision_no: document.getElementById("docRevisionNo").value || null,
      revision_date: document.getElementById("docRevisionDate").value || null,
      owner: document.getElementById("docOwner").value || null,
      file_link: document.getElementById("docFileLink").value || null,
      tags: normalizeTagsInput(document.getElementById("docTags").value) || null,
      note: document.getElementById("docNote").value || null,
    };
    try {
      let doc;
      if (id) {
        doc = await api(`/api/documents/${id}`, { method: "PUT", body: JSON.stringify(payload) });
        toast("수정했습니다.");
      } else {
        doc = await api("/api/documents", { method: "POST", body: JSON.stringify(payload) });
        toast("추가했습니다.");
      }
      await syncDocumentLawMappings(doc.id);
      resetDocumentForm();
      closeDocumentModal();
      loadDocuments();
      loadDashboard();
    } catch (e) {
      toast(`저장 실패: ${e.message}`, true);
    }
  });
  document.getElementById("docCancelBtn").addEventListener("click", () => {
    resetDocumentForm();
    closeDocumentModal();
  });
  document.getElementById("docModalCloseBtn").addEventListener("click", () => {
    resetDocumentForm();
    closeDocumentModal();
  });
  document.getElementById("docAddBtn").addEventListener("click", () => {
    resetDocumentForm();
    openDocumentModal();
  });
  document.getElementById("documentModalOverlay").addEventListener("click", (ev) => {
    if (ev.target.id === "documentModalOverlay") {
      resetDocumentForm();
      closeDocumentModal();
    }
  });
  document.getElementById("docLawCategoryFilter").addEventListener("change", renderDocLawCheckboxes);
  document.getElementById("docLawSearchInput").addEventListener("input", renderDocLawCheckboxes);
}
