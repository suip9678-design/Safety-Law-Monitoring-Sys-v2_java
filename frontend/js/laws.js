// "법령 마스터" 탭: 추적 중인 법령/고시 목록, 신규 검색·등록, 플랜트건설업
// 기본 법령 세트 일괄 추가.

import { state, api, toast, fmtDate, fmtDateTime, escapeHtml, statusBadge, SOURCE_TYPE_LABEL, lawReasonDocUrl } from "./core.js";
import { viewRevisionsForLaw } from "./tabs.js";

// 플랜트건설업에 저촉되는 안전보건 관련 법령·고시 기본 세트.
// 실제 국가법령정보센터에서 이름으로 검색해 첫 번째 결과를 추가하는 방식이라,
// 정확한 공식 명칭과 약간 다르더라도 유사 검색으로 찾아질 수 있습니다.
const DEFAULT_LAW_SET = [
  "산업안전보건법",
  "산업안전보건법 시행령",
  "산업안전보건법 시행규칙",
  "산업안전보건기준에 관한 규칙",
  "중대재해 처벌 등에 관한 법률",
  "중대재해 처벌 등에 관한 법률 시행령",
  "건설산업기본법",
  "건설기술 진흥법",
  "건설기술 진흥법 시행령",
  "시설물의 안전 및 유지관리에 관한 특별법",
  "위험물안전관리법",
  "고압가스 안전관리법",
  "화학물질관리법",
  "화학물질의 등록 및 평가 등에 관한 법률",
  "전기안전관리법",
  "소방시설 설치 및 관리에 관한 법률",
];

const DEFAULT_ADMRUL_SET = [
  "위험성평가 실시규정",
  "유해ㆍ위험방지계획서 제출ㆍ심사 및 확인업무 처리에 관한 규정",
  "건설공사 안전관리 업무수행 지침",
  "관리감독자 안전보건교육 운영지침",
  "크레인 안전작업지침",
  "추락재해방지 표준안전작업지침",
];

export function lawCategoryRank(category) {
  // 법 -> 시행령 -> 시행규칙 -> 고시/예규/훈령 순으로 묶어서 정렬하기 위한 순위
  if (category === "법률") return 0;
  if (category === "대통령령") return 1;
  if (category && category.endsWith("부령")) return 2; // ...부령 = 시행규칙류
  return 3; // 고시/예규/훈령 등 행정규칙
}

export function sortLaws(laws) {
  return [...laws].sort((a, b) => {
    const rankDiff = lawCategoryRank(a.category) - lawCategoryRank(b.category);
    if (rankDiff !== 0) return rankDiff;
    return (a.name || "").localeCompare(b.name || "", "ko");
  });
}

const LAW_CATEGORY_GROUP_LABEL = ["법률", "대통령령(시행령)", "부령(시행규칙)", "고시·예규·훈령 등(행정규칙)"];

let lawsFilterText = "";

export async function loadLaws() {
  try {
    state.laws = sortLaws(await api("/api/laws"));
    renderLawsTable();
  } catch (e) {
    toast(`법령 목록 로드 실패: ${e.message}`, true);
  }
}

function renderLawsTable() {
  const el = document.getElementById("lawsTable");
  if (!state.laws.length) {
    el.innerHTML = `<div class="empty">관리중인 법령이 없습니다. 위에서 검색해 등록하세요.</div>`;
    return;
  }

  const q = lawsFilterText.trim();
  const filtered = q
    ? state.laws.filter((l) => (l.name || "").includes(q) || (l.department || "").includes(q))
    : state.laws;
  if (!filtered.length) {
    el.innerHTML = `<div class="empty">"${escapeHtml(q)}"와(과) 일치하는 법령이 없습니다.</div>`;
    return;
  }

  // state.laws는 loadLaws()에서 이미 법 -> 시행령 -> 시행규칙 -> 고시 순으로
  // 정렬되어 있으므로(sortLaws), 여기서는 그 순서를 그대로 이용해 구간마다
  // 그룹 제목행을 끼워넣기만 하면 됨.
  const rows = [];
  let lastRank = null;
  for (const l of filtered) {
    const rank = lawCategoryRank(l.category);
    if (rank !== lastRank) {
      const count = filtered.filter((x) => lawCategoryRank(x.category) === rank).length;
      rows.push(`<tr class="law-group-row"><td colspan="8">${LAW_CATEGORY_GROUP_LABEL[rank]} <span class="hint">${count}건</span></td></tr>`);
      lastRank = rank;
    }
    const reasonUrl = lawReasonDocUrl({
      source_type: l.source_type,
      external_id: l.external_id,
      enforcement_date: l.current_enforcement_date,
    });
    const promCell = reasonUrl
      ? `<a href="${escapeHtml(reasonUrl)}" target="_blank" rel="noopener" title="법령정보센터: 제정·개정이유 보기">${fmtDate(l.current_promulgation_date)}</a>`
      : fmtDate(l.current_promulgation_date);
    rows.push(`
          <tr class="${l.unreviewed_revision_count ? "law-row-alert" : ""}">
            <td>${l.detail_link
              ? `<a href="${escapeHtml(l.detail_link)}" target="_blank" rel="noopener">${escapeHtml(l.name)}</a>`
              : escapeHtml(l.name)}</td>
            <td>${escapeHtml(l.category || "-")}</td>
            <td>${l.unreviewed_revision_count
              ? `<button class="link-btn" data-view-revisions="${l.id}" data-law-name="${escapeHtml(l.name)}" title="이 법령의 개정 이력 보기">${statusBadge("미검토")} ${l.unreviewed_revision_count}</button>`
              : "-"}</td>
            <td>${promCell}</td>
            <td>${fmtDate(l.current_enforcement_date)}</td>
            <td>${l.mapped_document_count}</td>
            <td>${fmtDateTime(l.last_synced_at)}</td>
            <td><button class="link-btn" data-remove-law="${l.id}">취소</button></td>
          </tr>
        `);
  }

  el.innerHTML = `
    <table>
      <thead><tr>
        <th>법령/고시</th><th>구분</th><th>미검토 개정</th><th>공포일자</th><th>시행일자</th><th>매핑 문서</th><th>마지막 확인</th><th></th>
      </tr></thead>
      <tbody>${rows.join("")}</tbody>
    </table>
  `;
  el.querySelectorAll("[data-remove-law]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("취소할까요? (개정 이력은 유지됩니다)")) return;
      try {
        await api(`/api/laws/${btn.dataset.removeLaw}`, { method: "DELETE" });
        toast("취소했습니다.");
        loadLaws();
      } catch (e) {
        toast(`실패: ${e.message}`, true);
      }
    });
  });
  el.querySelectorAll("[data-view-revisions]").forEach((btn) => {
    btn.addEventListener("click", () => {
      viewRevisionsForLaw(Number(btn.dataset.viewRevisions), btn.dataset.lawName);
    });
  });
}

export async function fetchLawSearch(sourceType, query) {
  return api(`/api/laws/search?source_type=${sourceType}&query=${encodeURIComponent(query)}`);
}

function isAlreadyTracked(r) {
  return state.laws.some((l) =>
    (r.master_id && l.master_id && l.master_id === r.master_id) ||
    (l.source_type === r.source_type && l.external_id === r.external_id) ||
    (l.source_type === r.source_type && l.name === r.name)
  );
}

let searchLawsSeq = 0;

export async function searchLaws() {
  const sourceType = document.getElementById("searchSourceType").value;
  const query = document.getElementById("searchQuery").value.trim();
  if (!query) {
    document.getElementById("searchResults").innerHTML = "";
    return;
  }
  const mySeq = ++searchLawsSeq;
  const el = document.getElementById("searchResults");
  el.innerHTML = `<div class="empty">검색 중...</div>`;
  try {
    const results = sourceType === "all"
      ? (await Promise.all([fetchLawSearch("law", query), fetchLawSearch("admrul", query)])).flat()
      : await fetchLawSearch(sourceType, query);

    if (mySeq !== searchLawsSeq) return; // 더 최근 검색이 이미 진행 중이면 이 결과는 버림

    if (!results.length) {
      el.innerHTML = `<div class="empty">검색 결과가 없습니다.</div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead><tr><th>법령/고시</th><th>출처</th><th>구분</th><th>소관부처</th><th>공포일자</th><th>시행일자</th><th></th></tr></thead>
        <tbody>
          ${results.map((r, i) => {
            const tracked = isAlreadyTracked(r);
            return `
            <tr>
              <td>${escapeHtml(r.name || "-")}</td>
              <td>${SOURCE_TYPE_LABEL[r.source_type] || escapeHtml(r.source_type)}</td>
              <td>${escapeHtml(r.category || "-")}</td>
              <td>${escapeHtml(r.department || "-")}</td>
              <td>${fmtDate(r.promulgation_date)}</td>
              <td>${fmtDate(r.enforcement_date)}</td>
              <td>${tracked
                ? `<button class="btn" disabled title="이미 관리중인 법령입니다">등록됨</button>`
                : `<button class="btn" data-add-result="${i}">등록</button>`}</td>
            </tr>
          `;
          }).join("")}
        </tbody>
      </table>
    `;
    el.querySelectorAll("[data-add-result]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const r = results[Number(btn.dataset.addResult)];
        btn.disabled = true;
        btn.textContent = "등록 중...";
        try {
          await api("/api/laws", {
            method: "POST",
            body: JSON.stringify({
              source_type: r.source_type,
              external_id: r.external_id,
              master_id: r.master_id,
              name: r.name,
              category: r.category,
              department: r.department,
              promulgation_no: r.promulgation_no,
              promulgation_date: r.promulgation_date,
              enforcement_date: r.enforcement_date,
              detail_link: r.detail_link,
            }),
          });
          toast(`"${r.name}" 추적을 시작했습니다.`);
          // 여러 건을 연달아 등록할 때 어디까지 눌렀는지 헷갈리지 않도록,
          // 재검색 없이도 이 버튼 자체를 바로 "등록 완료"로 바꿔준다.
          btn.textContent = "등록 완료";
          loadLaws();
        } catch (e) {
          toast(`추가 실패: ${e.message}`, true);
          btn.disabled = false;
          btn.textContent = "등록";
        }
      });
    });
  } catch (e) {
    if (mySeq !== searchLawsSeq) return;
    el.innerHTML = `<div class="empty">검색 실패: ${escapeHtml(e.message)}</div>`;
  }
}

export async function seedDefaultLaws() {
  const btn = document.getElementById("seedDefaultsBtn");
  const el = document.getElementById("seedResults");
  btn.disabled = true;
  btn.textContent = "추가 중...";
  const rows = [];

  const runSet = async (sourceType, names) => {
    for (const name of names) {
      try {
        const results = await fetchLawSearch(sourceType, name);
        if (!results.length) {
          rows.push({ name, status: "검색 결과 없음" });
          continue;
        }
        const match = results[0];
        try {
          await api("/api/laws", {
            method: "POST",
            body: JSON.stringify({
              source_type: match.source_type,
              external_id: match.external_id,
              master_id: match.master_id,
              name: match.name,
              category: match.category,
              department: match.department,
              promulgation_no: match.promulgation_no,
              promulgation_date: match.promulgation_date,
              enforcement_date: match.enforcement_date,
              detail_link: match.detail_link,
            }),
          });
          rows.push({ name: match.name, status: "추가됨" });
        } catch (e) {
          rows.push({ name: match.name, status: e.message.includes("이미") ? "이미 추적 중" : `실패: ${e.message}` });
        }
      } catch (e) {
        rows.push({ name, status: `검색 실패: ${e.message}` });
      }
    }
  };

  await runSet("law", DEFAULT_LAW_SET);
  await runSet("admrul", DEFAULT_ADMRUL_SET);

  el.innerHTML = `
    <table>
      <thead><tr><th>법령/고시</th><th>결과</th></tr></thead>
      <tbody>
        ${rows.map((r) => `<tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.status)}</td></tr>`).join("")}
      </tbody>
    </table>
  `;
  const addedCount = rows.filter((r) => r.status === "추가됨").length;
  toast(`기본 법령 세트 처리 완료: ${addedCount}건 추가 (총 ${rows.length}건 시도)`);
  btn.disabled = false;
  btn.textContent = "기본 법령 세트 추가";
  loadLaws();
}

export function initLawsTab() {
  document.getElementById("searchBtn").addEventListener("click", searchLaws);
  document.getElementById("searchQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); searchLaws(); } });
  let searchDebounceTimer = null;
  document.getElementById("searchQuery").addEventListener("input", () => {
    clearTimeout(searchDebounceTimer);
    const query = document.getElementById("searchQuery").value.trim();
    if (query.length < 2) { document.getElementById("searchResults").innerHTML = ""; return; }
    searchDebounceTimer = setTimeout(searchLaws, 400);
  });
  document.getElementById("searchSourceType").addEventListener("change", () => {
    if (document.getElementById("searchQuery").value.trim().length >= 2) searchLaws();
  });
  document.getElementById("seedDefaultsBtn").addEventListener("click", seedDefaultLaws);
  document.getElementById("lawsFilterInput").addEventListener("input", (e) => {
    lawsFilterText = e.target.value;
    renderLawsTable();
  });
}
