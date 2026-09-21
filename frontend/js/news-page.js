// "안전보건 뉴스" 탭: 대시보드 게시판(최신 몇 건 자동 스크롤)과 달리, 예전
// 기사를 찾거나 특정 기간의 사고/이슈를 모아보려면 검색이 필요하다.
// 카테고리/키워드는 즉시 반응하고(입력 중엔 디바운스), 날짜 범위는 시작일 >
// 종료일 같은 실수를 막기 위해 "검색" 버튼(또는 폼 제출)을 눌러야 반영된다.
// 실제 필터링(카테고리, 제목 키워드, 날짜 범위)은 모두 서버(/api/news/search)
// 에서 수행한다 - 날짜는 published_at(없으면 fetched_at) 기준이라 클라이언트
// 에 이미 내려받은 목록만으로는 정확히 거를 수 없기 때문이다.

import { api, toast, escapeHtml } from "./core.js";

const newsPageState = { category: "", q: "", dateFrom: "", dateTo: "", archivedOnly: false };

// 검색어가 없으면(날짜/카테고리/보관함 필터만 걸었을 때) 그래도 뭔가 검색은
// 되도록 카테고리에 맞는 기본 검색어를 대신 쓴다.
const NEWS_CATEGORY_SEARCH_HINT = { moel: "고용노동부 안전보건", kosha: "안전보건공단", accident: "중대재해 사망", issue: "안전보건 이슈" };

function externalNewsSearchQuery() {
  return newsPageState.q || NEWS_CATEGORY_SEARCH_HINT[newsPageState.category] || "안전보건 중대재해";
}

// 보관해둔(또는 서버에 아직 저장돼 있는) 뉴스 중에는 찾는 내용이 없을 수
// 있다 - 보관 기간이 지나 이미 정리됐거나, 애초에 이 서버가 다루는 3개
// 피드에 뜬 적이 없는 기사일 수 있어서다. 그럴 때 화면이 막다른 길이
// 되지 않도록, 같은 검색어로 구글 뉴스를 새 탭에서 바로 열어주는 링크를
// 보여준다(별도 서버 호출 없이 브라우저에서 직접 조회).
function buildExternalNewsSearchUrl(query) {
  return `https://news.google.com/search?q=${encodeURIComponent(query)}&hl=ko&gl=KR&ceid=KR:ko`;
}

function fmtNewsDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const datePart = d.toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" });
  const timePart = d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${datePart} ${timePart}`;
}

function renderNewsPageResults(data) {
  const el = document.getElementById("newsPageResults");
  const items = data.items || [];
  const total = data.total || 0;
  document.getElementById("newsPageDemoBadge").hidden = !items.some((n) => n.is_demo);

  const hasFilter = !!(newsPageState.q || newsPageState.category || newsPageState.dateFrom || newsPageState.dateTo || newsPageState.archivedOnly);
  document.getElementById("newsPageSearchStatus").textContent = total
    ? `총 ${total}건${items.length < total ? ` 중 최근 ${items.length}건 표시 (검색어를 좁혀보세요)` : ""}`
    : "";

  if (!items.length) {
    if (!hasFilter) {
      el.innerHTML = `<div class="empty">표시할 뉴스가 없습니다. 설정 &gt; 안전보건 뉴스 게시판에서 "지금 새로고침"을 눌러보세요.</div>`;
      return;
    }
    const query = externalNewsSearchQuery();
    const externalUrl = buildExternalNewsSearchUrl(query);
    const scopeLabel = newsPageState.archivedOnly ? "보관함에 " : "";
    el.innerHTML = `
      <div class="empty">
        ${scopeLabel}지정한 조건에 맞는 뉴스가 없습니다. 검색어나 날짜 범위를 조정해보거나,
        아래 버튼으로 외부 브라우저에서 바로 찾아보세요.
        <div style="margin-top: 12px;">
          <a class="btn btn-primary" style="display: inline-block;" href="${escapeHtml(externalUrl)}" target="_blank" rel="noopener">
            외부 브라우저에서 "${escapeHtml(query)}" 검색하기
          </a>
        </div>
      </div>
    `;
    return;
  }

  el.innerHTML = `
    <table>
      <thead><tr><th>구분</th><th>제목</th><th>게시일</th><th></th></tr></thead>
      <tbody>
        ${items
          .map(
            (n) => `
              <tr>
                <td><span class="news-board-source news-src-${n.category}">${escapeHtml(n.source_name)}</span></td>
                <td>
                  <a href="${escapeHtml(n.link)}" target="_blank" rel="noopener">${escapeHtml(n.title)}</a>
                  ${n.is_demo ? '<span class="badge badge-warn">예시</span>' : ""}
                  ${n.is_archived ? '<span class="badge badge-ok">보관됨</span>' : ""}
                </td>
                <td>${fmtNewsDateTime(n.published_at || n.fetched_at)}</td>
                <td><button type="button" class="link-btn" data-toggle-archive="${n.id}" data-archived="${n.is_archived ? "1" : ""}">${
                  n.is_archived ? "보관 해제" : "보관"
                }</button></td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
  el.querySelectorAll("[data-toggle-archive]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const nextArchived = !btn.dataset.archived;
      btn.disabled = true;
      try {
        await api(`/api/news/${btn.dataset.toggleArchive}/archive`, {
          method: "PATCH",
          body: JSON.stringify({ is_archived: nextArchived }),
        });
        loadNewsPage();
      } catch (e) {
        toast(`보관 처리 실패: ${e.message}`, true);
        btn.disabled = false;
      }
    });
  });
}

export async function loadNewsPage() {
  const params = new URLSearchParams();
  if (newsPageState.category) params.set("category", newsPageState.category);
  if (newsPageState.q) params.set("q", newsPageState.q);
  if (newsPageState.dateFrom) params.set("date_from", newsPageState.dateFrom);
  if (newsPageState.dateTo) params.set("date_to", newsPageState.dateTo);
  if (newsPageState.archivedOnly) params.set("archived", "true");
  try {
    const data = await api(`/api/news/search${params.toString() ? `?${params.toString()}` : ""}`);
    renderNewsPageResults(data);
  } catch (e) {
    toast(`뉴스 검색 실패: ${e.message}`, true);
  }
}

export function initNewsPage() {
  document.querySelectorAll("#newsPageCategoryFilters .news-filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#newsPageCategoryFilters .news-filter-btn").forEach((b) => b.classList.toggle("active", b === btn));
      newsPageState.category = btn.dataset.cat || "";
      loadNewsPage();
    });
  });

  document.getElementById("newsPageSearchForm").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const dateFrom = document.getElementById("newsPageDateFrom").value;
    const dateTo = document.getElementById("newsPageDateTo").value;
    if (dateFrom && dateTo && dateFrom > dateTo) {
      toast("시작일이 종료일보다 늦을 수 없습니다.", true);
      return;
    }
    newsPageState.q = document.getElementById("newsPageQueryInput").value.trim();
    newsPageState.dateFrom = dateFrom;
    newsPageState.dateTo = dateTo;
    newsPageState.archivedOnly = document.getElementById("newsPageArchivedOnly").checked;
    loadNewsPage();
  });

  document.getElementById("newsPageArchivedOnly").addEventListener("change", (e) => {
    newsPageState.archivedOnly = e.target.checked;
    loadNewsPage();
  });

  let newsPageDebounceTimer = null;
  document.getElementById("newsPageQueryInput").addEventListener("input", (e) => {
    clearTimeout(newsPageDebounceTimer);
    newsPageDebounceTimer = setTimeout(() => {
      newsPageState.q = e.target.value.trim();
      loadNewsPage();
    }, 400);
  });

  document.getElementById("newsPageResetBtn").addEventListener("click", () => {
    newsPageState.category = "";
    newsPageState.q = "";
    newsPageState.dateFrom = "";
    newsPageState.dateTo = "";
    newsPageState.archivedOnly = false;
    document.getElementById("newsPageQueryInput").value = "";
    document.getElementById("newsPageDateFrom").value = "";
    document.getElementById("newsPageDateTo").value = "";
    document.getElementById("newsPageArchivedOnly").checked = false;
    document.querySelectorAll("#newsPageCategoryFilters .news-filter-btn").forEach((b) => b.classList.toggle("active", !b.dataset.cat));
    loadNewsPage();
  });
}
