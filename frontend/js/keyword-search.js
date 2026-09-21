// "키워드 검색" 탭: 본문 캐시(ScrapedLawContent) 대상 키워드/문장 검색.

import { api, escapeHtml, fmtDate, SOURCE_TYPE_LABEL } from "./core.js";
import { activateTab } from "./tabs.js";

const MATCHED_IN_LABEL = { name: "법령명", content: "본문" };

export function highlightSnippet(snippet, query) {
  const escaped = escapeHtml(snippet);
  const q = escapeHtml(query);
  if (!q) return escaped;
  return escaped.split(q).join(`<mark>${q}</mark>`);
}

// 크롬/엣지 등이 지원하는 "텍스트 조각 링크"(Scroll To Text Fragment,
// #:~:text=...) - 대상 페이지에 아무 코드가 없어도 브라우저가 그 문구를
// 찾아 스크롤하고 노란색으로 하이라이트해준다(Ctrl+F로 찾은 것과 비슷한
// 효과). 법제처 페이지 코드를 건드릴 수 없으니 이 방법으로 검색어를
// 눈에 띄게 한다. 파이어폭스/사파리는 아직 지원하지 않아 그런 브라우저는
// 그냥 평범한 이동 링크로만 동작한다.
function withTextHighlight(url, query) {
  if (!url || !query) return url;
  return `${url}#:~:text=${encodeURIComponent(query)}`;
}

let keywordSearchSeq = 0;

export async function searchKeywords() {
  const sourceType = document.getElementById("keywordSearchSourceType").value;
  const query = document.getElementById("keywordSearchInput").value.trim();
  const el = document.getElementById("keywordSearchResults");
  if (!query) { el.innerHTML = ""; return; }
  const mySeq = ++keywordSearchSeq;
  el.innerHTML = `<div class="empty">검색 중...</div>`;
  try {
    const results = await api(`/api/content-cache/search?source_type=${sourceType}&query=${encodeURIComponent(query)}`);
    if (mySeq !== keywordSearchSeq) return;
    if (!results.length) {
      el.innerHTML = `<div class="empty">검색 결과가 없습니다. 설정 &gt; 법령 본문 캐시를 먼저 새로고침해보세요.</div>`;
      return;
    }
    el.innerHTML = `
      <table>
        <thead><tr><th>법령/고시</th><th>출처</th><th>구분</th><th>소관부처</th><th>매칭 위치</th><th>미리보기</th><th>시행일자</th></tr></thead>
        <tbody>
          ${results.map((r) => `
            <tr>
              <td>${r.detail_link
                ? `<a href="${escapeHtml(withTextHighlight(r.detail_link, query))}" target="_blank" rel="noopener">${escapeHtml(r.name)}</a>`
                : escapeHtml(r.name)}</td>
              <td>${SOURCE_TYPE_LABEL[r.source_type] || escapeHtml(r.source_type)}</td>
              <td>${escapeHtml(r.category || "-")}</td>
              <td>${escapeHtml(r.department || "-")}</td>
              <td>${MATCHED_IN_LABEL[r.matched_in] || "-"}</td>
              <td class="search-snippet">${(() => {
                if (!r.snippet) return '<span class="hint">-</span>';
                const href = withTextHighlight(r.article_link || r.detail_link, query);
                const title = r.article_link ? "해당 조문으로 이동" : "법령 상세 페이지로 이동";
                return href
                  ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener" title="${title}">${highlightSnippet(r.snippet, query)}</a>`
                  : highlightSnippet(r.snippet, query);
              })()}</td>
              <td>${fmtDate(r.enforcement_date)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    if (mySeq !== keywordSearchSeq) return;
    el.innerHTML = `<div class="empty">검색 실패: ${escapeHtml(e.message)}</div>`;
  }
}

export function initKeywordSearch() {
  document.getElementById("keywordSearchBtn").addEventListener("click", searchKeywords);
  document.getElementById("keywordSearchInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); searchKeywords(); }
  });
  document.getElementById("keywordSearchSourceType").addEventListener("change", () => {
    if (document.getElementById("keywordSearchInput").value.trim()) searchKeywords();
  });
  document.getElementById("dashboardKeywordSearchForm").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const query = document.getElementById("dashboardKeywordSearchInput").value.trim();
    if (!query) return;
    document.getElementById("keywordSearchInput").value = query;
    activateTab("keyword-search");
    searchKeywords();
  });
}
