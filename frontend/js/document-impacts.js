// 법령이 아니라 "어떤 절차서/지침서를 검토해야 하는가"를 기준으로 개정
// 이력을 보여주는 표. 대시보드("사내 절차서·지침서 개정 필요 사항")와
// 사규 개정 이력 탭 둘 다 같은 형식을 쓰므로 여기 하나로 모아둔다.

import { escapeHtml, fmtDate, statusSelect } from "./core.js";

// 문서명/구분은 rowspan으로 그 문서의 개정 건수만큼 세로로 합쳐서, 법령/
// 시행일/상태가 문서명/구분과 같은 표·같은 헤더 행에 나란히 놓이도록 한다.
export function renderDocumentImpactsList(docImpacts) {
  return `
    <table>
      <thead><tr><th>문서명</th><th>구분</th><th>법령</th><th>시행일</th><th>상태</th></tr></thead>
      <tbody>
        ${docImpacts.map((d) => d.revisions.map((r, i) => `
          <tr>
            ${i === 0 ? `
              <td rowspan="${d.revisions.length}">${escapeHtml(d.document_title)}</td>
              <td rowspan="${d.revisions.length}">${escapeHtml(d.doc_type)}</td>
            ` : ""}
            <td>${escapeHtml(r.tracked_law_name)}${r.matched_by === "tag" ? ' <span class="tag-badge" title="근거 법령으로 직접 매핑하지 않았지만, 문서 키워드가 이 법령의 이름/본문과 겹쳐 자동으로 매칭됨">#태그매칭</span>' : ""}</td>
            <td>${fmtDate(r.enforcement_date)}</td>
            <td>${statusSelect(r.id, r.review_status)}</td>
          </tr>
        `).join("")).join("")}
      </tbody>
    </table>
  `;
}
