// 대시보드 탭: 요약 카드, 법령 개정 리스트(quick), 사내 절차서/지침서
// 개정 필요 사항, 신규 제정 고시 후보, 알림 종 갱신, 뉴스 게시판 로드까지
// 진입점 하나(loadDashboard)로 묶는다.

import { api, toast, escapeHtml, fmtDate, fmtDateTime, lawReasonDocUrl } from "./core.js";
import { renderDocumentImpactsList } from "./document-impacts.js";
import { wireStatusSelects } from "./status-actions.js";
import { updateAlarmBell } from "./alarm.js";
import { loadNewsBoard, refreshNewsBoardInBackground } from "./news.js";
import { renderRevisionsList } from "./revisions.js";
import { loadLaws } from "./laws.js";

export function renderDashboardRevisionList(containerId, revisions, emptyMessage) {
  const el = document.getElementById(containerId);
  el.innerHTML = revisions.length ? renderRevisionsList(revisions, "quick") : `<div class="empty">${emptyMessage}</div>`;
  wireStatusSelects(el);
}

export function renderDashboardDocumentImpacts(containerId, docImpacts, emptyMessage) {
  const el = document.getElementById(containerId);
  el.innerHTML = docImpacts.length ? renderDocumentImpactsList(docImpacts) : `<div class="empty">${emptyMessage}</div>`;
  wireStatusSelects(el);
}

// "신규 제정 고시" 후보 - 등록해둔 게 개정된 게 아니라, 아직 등록 안 한
// 고시가 소관부처+키워드 이중 필터를 통과해 새로 발견된 경우.
export function renderNewAdmrulCandidates(containerId, candidates, emptyMessage) {
  const el = document.getElementById(containerId);
  if (!candidates.length) {
    el.innerHTML = `<div class="empty">${emptyMessage}</div>`;
    return;
  }
  el.innerHTML = `
    <table>
      <thead><tr><th>법령/고시</th><th>구분</th><th>소관부처</th><th>공포일자</th><th>매칭 키워드</th><th></th></tr></thead>
      <tbody>
        ${candidates.map((c) => {
        const reasonUrl = lawReasonDocUrl({
          source_type: c.source_type,
          external_id: c.external_id,
          enforcement_date: c.enforcement_date,
        });
        return `
          <tr>
            <td>${c.detail_link
              ? `<a href="${escapeHtml(c.detail_link)}" target="_blank" rel="noopener">${escapeHtml(c.name)}</a>`
              : escapeHtml(c.name)}</td>
            <td>${escapeHtml(c.category || "-")}</td>
            <td>${escapeHtml(c.department || "-")}</td>
            <td>${reasonUrl
              ? `<a href="${escapeHtml(reasonUrl)}" target="_blank" rel="noopener" title="법령정보센터: 제정·개정이유 보기">${fmtDate(c.promulgation_date)}</a>`
              : fmtDate(c.promulgation_date)}</td>
            <td><span class="hint">${escapeHtml(c.matched_keyword || "-")}</span></td>
            <td>
              <button class="btn btn-primary" data-track-candidate="${c.id}">등록</button>
              <button class="link-btn" data-dismiss-candidate="${c.id}">무시</button>
            </td>
          </tr>
        `;
      }).join("")}
      </tbody>
    </table>
  `;
  el.querySelectorAll("[data-track-candidate]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const c = candidates.find((x) => x.id === Number(btn.dataset.trackCandidate));
      if (!c) return;
      btn.disabled = true;
      btn.textContent = "등록 중...";
      try {
        await api("/api/laws", {
          method: "POST",
          body: JSON.stringify({
            source_type: c.source_type,
            external_id: c.external_id,
            master_id: c.master_id,
            name: c.name,
            category: c.category,
            department: c.department,
            promulgation_no: c.promulgation_no,
            promulgation_date: c.promulgation_date,
            enforcement_date: c.enforcement_date,
            detail_link: c.detail_link,
          }),
        });
        await api(`/api/laws/new-admrul-candidates/${c.id}/registered`, { method: "POST" });
        toast(`"${c.name}"을(를) 등록했습니다.`);
        loadDashboard();
        loadLaws();
      } catch (e) {
        toast(`등록 실패: ${e.message}`, true);
        btn.disabled = false;
        btn.textContent = "등록";
      }
    });
  });
  el.querySelectorAll("[data-dismiss-candidate]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/laws/new-admrul-candidates/${btn.dataset.dismissCandidate}/dismiss`, { method: "POST" });
        toast("무시했습니다. 다시 후보로 뜨지 않습니다.");
        loadDashboard();
      } catch (e) {
        toast(`처리 실패: ${e.message}`, true);
      }
    });
  });
}

export async function loadDashboard() {
  try {
    const s = await api("/api/dashboard/summary");
    document.getElementById("summaryCards").innerHTML = `
      <div class="card"><div class="value">${s.tracked_law_count}</div><div class="label">관리중인 법령</div></div>
      <div class="card"><div class="value">${s.unreviewed_count}</div><div class="label">미검토 개정</div></div>
      <div class="card"><div class="value">${s.in_review_count}</div><div class="label">검토중</div></div>
      <div class="card"><div class="value">${s.reflected_count}</div><div class="label">반영완료</div></div>
      <div class="card"><div class="value">${s.document_count}</div><div class="label">등록된 사규</div></div>
    `;
    document.getElementById("lastSyncInfo").textContent = `마지막 동기화: ${fmtDateTime(s.last_sync_at)}`;
    renderDashboardRevisionList("recentLawRevisions", s.recent_revisions, `아직 감지된 개정이 없습니다. "새로고침"을 눌러 확인해보세요.`);
    renderNewAdmrulCandidates("newAdmrulCandidates", s.new_admrul_candidates, `현재 발견된 신규 제정 고시 후보가 없습니다.`);
    renderDashboardDocumentImpacts("recentDocImpacts", s.recent_document_impacts, `현재 개정 검토가 필요한 문서가 없습니다.`);
    updateAlarmBell(s);
  } catch (e) {
    toast(`대시보드 로드 실패: ${e.message}`, true);
  }
  loadNewsBoard();
  refreshNewsBoardInBackground();
}
