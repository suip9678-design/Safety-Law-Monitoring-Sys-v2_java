// statusSelect()(core.js)로 그려진 상태 변경 드롭다운의 공통 배선.
// 대시보드, 개정 이력 탭, 사규 개정 이력 탭이 모두 같은 드롭다운을 쓰므로
// 여기서 한 번만 구현한다 - 상태를 바꾸면 어디서 바꿨든 화면들을 전부
// 다시 불러온다(statusSelect의 색상은 렌더링 시점의 클래스로 고정되므로,
// 바꾼 화면 자신도 다시 그려야 색이 새 상태에 맞게 바뀐다).
//
// 이 모듈은 dashboard/revisions/doc-revisions 세 화면 모듈을 모두
// 가져오고, 그 세 모듈은 각자 자기 표를 그린 뒤 이 모듈의
// wireStatusSelects()를 다시 가져오는 순환 참조 구조다. 실제 호출은
// 전부 이벤트(드롭다운 change) 발생 시점에만 일어나 각 모듈이 이미 완전히
// 로드된 뒤이므로 문제가 없다.

import { api, toast } from "./core.js";
import { loadDashboard } from "./dashboard.js";
import { loadRevisions } from "./revisions.js";
import { loadDocRevisions } from "./doc-revisions.js";

export function wireStatusSelects(el) {
  el.querySelectorAll("[data-status-select]").forEach((sel) => {
    sel.addEventListener("change", async () => {
      try {
        await api(`/api/revisions/${sel.dataset.statusSelect}`, {
          method: "PATCH",
          body: JSON.stringify({ review_status: sel.value }),
        });
        toast("상태를 업데이트했습니다.");
        loadDocRevisions();
        loadDashboard();
        loadRevisions();
      } catch (e) {
        toast(`업데이트 실패: ${e.message}`, true);
      }
    });
  });
}
