// 공통 상태 + 어디서나 쓰는 기본 헬퍼(API 호출, 토스트, 문자열/날짜 포맷,
// 상태 배지). 다른 모든 모듈이 이 모듈을 가져다 쓰므로, 이 파일은 반대로
// 다른 화면별 모듈을 가져오지 않는다(순환 참조의 뿌리가 되지 않게).

export const state = {
  laws: [],
  documents: [],
  koshaGuides: [],
  revisionsLawFilter: null, // { id, name } | null
};

export const SOURCE_TYPE_LABEL = { law: "법령", admrul: "행정규칙" };

// 공포일자를 누르면 법제처(law.go.kr)의 "제정·개정이유" 페이지로 이동시키기
// 위한 URL. law.go.kr에서 확인된 URL 패턴이라 법률/시행령/시행규칙(law)에만
// 적용하고, 행정규칙(admrul, 고시/예규/훈령)에는 이 패턴이 통하지 않아 적용하지
// 않는다 - 법령 마스터/대시보드/개정 이력 어디서나 같은 규칙으로 링크를 만든다.
export function lawReasonDocUrl({ source_type, external_id, enforcement_date } = {}) {
  if (source_type !== "law" || !external_id || !enforcement_date) return null;
  const params = new URLSearchParams({
    lsiSeq: external_id,
    lsId: "",
    efYd: enforcement_date,
    chrClsCd: "010202",
    urlMode: "lsEfInfoR",
    viewCls: "lsRvsDocInfoR",
    ancYnChk: "0",
  });
  return `https://www.law.go.kr/lsInfoP.do?${params.toString()}#`;
}

export async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 4000);
}

export function fmtDate(d) {
  if (!d) return "-";
  return String(d).replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3");
}

export function fmtDateTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("ko-KR");
}

export function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const STATUS_BADGE_CLASS = { "미검토": "badge-pending", "검토중": "badge-progress", "반영완료": "badge-ok", "해당없음": "badge-warn" };

export function statusBadge(status) {
  return `<span class="badge ${STATUS_BADGE_CLASS[status] || ""}">${status}</span>`;
}

export function statusSelect(revisionId, status) {
  return `
    <select class="badge-select ${STATUS_BADGE_CLASS[status] || ""}" data-status-select="${revisionId}">
      ${["미검토", "검토중", "반영완료", "해당없음"].map((s) => `<option value="${s}" ${s === status ? "selected" : ""}>${s}</option>`).join("")}
    </select>
  `;
}
