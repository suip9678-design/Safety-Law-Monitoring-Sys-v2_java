# Python → Java 전환 설계 (안전보건 법령·고시 개정 추적 시스템 v2)

- 작성일: 2026-09-21
- 상태: 사용자 승인(A안) 완료, 스펙 검토 대기

## 1. 목표와 범위

사내 시스템에 올리기 위해 현재 Python(FastAPI + SQLAlchemy + SQLite) 백엔드를 아래 환경의 Java로 전환한다.

| 항목 | 값 |
|---|---|
| 언어 | Java, JDK 17.0.18 LTS |
| 프레임워크 | Spring Boot 3.5.x (요청 문서상 3.5.15, 빌드 시 Maven에서 존재 여부 확인, 없으면 가장 가까운 3.5.x) |
| DB | Oracle Database 10g EE 10.2.0.4 (64bit) |

### 확정된 결정 (사용자 답변)

1. **배포 형태**: 미확정(담당자 확인 필요). 실행 JAR로 만들되 WAR 전환이 쉬운 구조로 둔다.
2. **외부 API 호출**: 사내 서버에서 바로 가능. 프록시 지원은 만들지 않는다(YAGNI).
3. **데이터 이관**: 없음. 빈 Oracle DB에서 새로 시작한다. 마이그레이션 도구는 만들지 않는다.
4. **접근 방식**: MyBatis + 순수 SQL(A안).

### 범위 밖

- 프론트엔드 재작성(그대로 재사용).
- Windows 설치 파일(Go 런처, NSIS, 내장 Python 런타임), `run.bat`, `run.ps1`, `render.yaml`, `scripts/sync_cli.py`, `.github/workflows/build-installer.yml` — 웹서버 배포에는 불필요하므로 Java 저장소에서 제외한다.
- SQLite/PostgreSQL 지원. Oracle 10g만 지원한다.

## 2. 핵심 원칙: API 계약 유지

엔드포인트 경로, HTTP 메서드, 상태 코드, JSON 필드명(snake_case), 응답 구조를 Python 버전과 동일하게 유지한다.
이렇게 하면 `frontend/`(HTML/CSS/JS)를 수정 없이 `src/main/resources/static/`에 복사해 쓸 수 있다.
Jackson은 `PropertyNamingStrategies.SNAKE_CASE`로 설정한다.

전환 대상 엔드포인트 (Python 라우터 기준):

| 그룹 | 경로 |
|---|---|
| health | `GET /api/health` |
| laws | `GET /api/laws/search`, `GET/POST /api/laws`, `GET/DELETE /api/laws/{id}`, `POST /api/laws/new-admrul-candidates/{id}/dismiss`, `GET /api/laws/new-admrul-candidates/dismissed`, `POST .../{id}/restore`, `POST .../bulk-restore`, `POST .../{id}/registered` |
| revisions | `GET /api/revisions`, `PATCH /api/revisions/bulk-status`, `POST /api/revisions/bulk-delete`, `PATCH /api/revisions/{id}` |
| documents | `GET/POST /api/documents`, `GET /api/documents/impacts`, `GET/PUT/DELETE /api/documents/{id}` |
| mappings | `GET/POST /api/mappings`, `DELETE /api/mappings/{id}` |
| sync | `POST /api/sync` |
| settings | `GET/PUT /api/settings`, `GET/POST /api/settings/help-shown` |
| dashboard | `GET /api/dashboard/summary` |
| content-cache | `GET /api/content-cache/status`, `POST /full-refresh`, `GET /full-refresh-status`, `GET /search`, `POST /refresh` |
| news | `GET /api/news`, `GET /api/news/search`, `PATCH /api/news/{id}/archive`, `POST /api/news/sync` |
| kosha-guides | `GET/POST /api/kosha-guides`, `GET /search`, `PUT/DELETE /{id}`, `POST/GET/DELETE /{id}/file`, `GET /{id}/original`, `POST /bulk-delete`, `POST /bulk-import`, `POST /sync`, `POST /cache-content` |

응답/요청 스키마의 상세 필드는 `backend/app/schemas.py`를 정본으로 하고, Java DTO는 그것을 1:1로 옮긴다.

## 3. 기술 스택과 구성 요소 매핑

| Python | Java |
|---|---|
| FastAPI 라우터 10개 | `@RestController` 10개 |
| `sync_service`, `content_cache_service`, `news_service`, `kosha_guide_*` | `@Service` |
| `law_api.py`, `kosha_guide_api.py` (httpx) | Spring `RestClient`(또는 JDK HttpClient) 기반 클라이언트 + 데모 클라이언트 |
| `models.py` (SQLAlchemy 11개 모델) | MyBatis Mapper(XML) + 도메인 클래스 |
| `schemas.py` (Pydantic) | 요청/응답 DTO(record 또는 클래스) + Bean Validation |
| `settings_store.py` | `SettingsService` (`app_settings` 테이블 + `application.yml` 기본값) |
| `config.py` + `.env` | `application.yml` + 환경변수(`@ConfigurationProperties`) |
| APScheduler | Spring `@Scheduled`(zone=`Asia/Seoul`) + 기동 시 따라잡기 |
| `BasicAuthMiddleware` | Spring Security HTTP Basic (계정 미설정 시 인증 비활성) |
| pypdf | Apache PDFBox |
| RSS/Atom 파싱(`news_service`) | JDK 내장 XML 파서(DocumentBuilder). Rome 등 추가 의존성은 쓰지 않는다 |
| `ensure_columns` 경량 마이그레이션 | 제거. `schema-oracle10g.sql` 1벌로 대체 |
| `StaticFiles(frontend)` | Spring Boot 정적 리소스(`classpath:/static/`) |

- 빌드 도구: Maven.
- 의존성: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-validation`, `mybatis-spring-boot-starter`(3.0.x), `ojdbc6`, `pdfbox`, 테스트용 `spring-boot-starter-test`, `h2`.
- Java 기본 패키지: `com.company.safetylaw` (사내 규칙이 있으면 교체).
- 패키지 구조: `config`, `controller`, `service`, `mapper`, `domain`, `dto`, `client`, `scheduler`.

## 4. Oracle 10g 대응

### 4.1 스키마 (`src/main/resources/db/schema-oracle10g.sql`)

테이블 11개: `tracked_laws`, `law_revisions`, `company_documents`, `document_law_mappings`, `new_admrul_candidates`, `scraped_law_contents`, `kosha_guides`, `app_settings`, `news_items` (+ 필요한 시퀀스).

| 규칙 | 이유 |
|---|---|
| PK는 시퀀스 + MyBatis `selectKey`(`SEQ.NEXTVAL`). 트리거는 만들지 않는다 | 10g에는 IDENTITY가 없다. 트리거 없이 단순화 |
| 문자열은 `VARCHAR2(n CHAR)` | 한글이 바이트 기준으로 잘리는 것을 막는다 |
| 긴 텍스트는 `CLOB` | `VARCHAR2`는 4000바이트 제한 |
| 불리언은 `NUMBER(1)` (0/1, `CHECK`) | `BOOLEAN` 컬럼 없음 |
| 일시는 `TIMESTAMP` | `DATETIME` 없음. 서버 UTC 저장 규칙은 Python과 동일하게 유지 |
| 법령 일자(공포일 등)는 `VARCHAR2(16 CHAR)` | Python 모델과 동일하게 문자열 유지 |
| 테이블, 제약조건, 시퀀스 이름은 30자 이하 | 10g 식별자 길이 제한 |
| 유니크 제약은 기존과 동일 | `(source_type, external_id)`, `(document_id, tracked_law_id)`, `(category, guid)`, `kosha_guides.code` 등. Oracle 유니크 인덱스는 NULL을 여러 건 허용하므로 `code`가 NULL인 가이드 다건 등록도 동일하게 동작 |
| `ON DELETE CASCADE` 대신 서비스 계층에서 자식부터 삭제 | SQLAlchemy의 `cascade="all, delete-orphan"` 동작을 유지하기 위함 |

### 4.2 SQL 작성 규칙

- 페이징/LIMIT은 `ROWNUM` 서브쿼리를 쓴다. `OFFSET/FETCH`, `LIMIT`은 사용하지 않는다.
- `LISTAGG`, `WITH ... RECURSIVE`, `MERGE ... DELETE` 등 11g 이상 기능은 쓰지 않는다. upsert가 필요하면 select 후 insert/update로 처리한다.
- CLOB 검색은 `DBMS_LOB.INSTR` 또는 `LIKE`를 쓴다. 대소문자 무시가 필요하면 `UPPER()`로 감싼다. 인덱스가 없는 전체 스캔이므로 수천 건 규모에서는 느릴 수 있음을 알린다.
- **빈 문자열은 NULL로 취급된다.** 저장 시 공백/빈 문자열은 `null`로 통일하고, 조회 결과의 `null`은 응답에서 Python이 내던 값(`null` 또는 `""`)에 맞춘다.
- 예외: `app_settings`는 "빈 값으로 저장한 행"과 "저장한 적 없음"을 구분해야 한다(현재 `settings_store.get_all`). Oracle에서는 빈 값이 NULL이 되므로 **값이 아니라 행 존재 여부**로 판단하고, `value`가 NULL이면 `""`로 해석한다.
- 뉴스의 `is_nonfatal_accident` 필터(제목에 사망 키워드가 없는 accident 카테고리)는 `title LIKE '%키워드%' OR ...` 조합의 SQL로 옮긴다. 키워드 목록은 Java 상수에서 파라미터로 주입한다.

### 4.3 JDBC 드라이버

- 10.2를 공식 지원하는 `ojdbc6`(11.2.0.4, JDBC 4.0)를 쓴다.
- Maven Central에 없으므로 사내 저장소 또는 `mvn install:install-file`로 로컬 설치한다. 저장소에 설치 방법을 문서화한다.
- JDK 17에서의 동작은 실제 사내 10g 개발 DB에서 확인해야 한다(아래 6절).
- 접속 URL은 SID 방식(`jdbc:oracle:thin:@host:1521:SID`)을 기본으로 한다. 서비스명 방식이 필요하면 설정으로 바꾼다.
- 커넥션 풀은 HikariCP. 검증 쿼리는 `SELECT 1 FROM DUAL`을 명시한다(ojdbc6의 `isValid` 지원 여부에 의존하지 않기 위해).

## 5. 동작 로직 이식

### 5.1 스케줄러 (`main.py` 대응)

| 작업 | 규칙 |
|---|---|
| 법령 자동 동기화 | `AUTO_SYNC_INTERVAL_HOURS > 0`일 때 해당 주기로 실행. 기동 직후 실행하지 않음 |
| 뉴스 동기화 | `NEWS_FETCH_INTERVAL_HOURS > 0`일 때 주기 실행, 기동 20초 후 첫 실행. 게시판 비활성 설정이면 건너뜀 |
| 일일 유지보수 | 매일 01:00 KST. 신규 제정 고시 탐지 → 후보 본문 캐시 새로고침 → (설정 켠 경우) 전체 법령 캐시. 각 단계 실패가 다음 단계를 막지 않는다 |
| 따라잡기 | 기동 시 `last_daily_maintenance_at`(`app_settings`)가 없거나 20시간 이상 지났으면 15초 후 1회 실행. 유지보수 종료 시 항상(`finally`) 실행 시각을 기록 |

- 시간대는 항상 `ZoneId.of("Asia/Seoul")`를 명시한다(시스템 시간대에 의존하지 않는다).
- 동시 실행 방지: 같은 작업이 이전 실행 중에 다시 돌지 않도록 작업별 `AtomicBoolean` 가드를 둔다. (기존 Python 버전의 `full-refresh-status` 진행 상태 조회와 같은 성격이다.)
- 전체 법령 캐시(`/api/content-cache/full-refresh`)는 백그라운드 스레드(`@Async` 또는 단일 스레드 Executor)에서 실행하고 진행 상태를 메모리에 유지한다.

### 5.2 설정 우선순위

`app_settings` 행이 있으면 그 값, 없으면 `application.yml`(환경변수) 기본값. 대시보드 설정 화면에서 바꾼 값이 서버 재시작 없이 즉시 반영되어야 한다.

### 5.3 외부 API 클라이언트

- 국가법령정보센터(`lawSearch.do`, `lawService.do`; target=`law`/`admrul`), 공공데이터포털 KOSHA 가이드, 뉴스 RSS/Atom.
- 인증키(OC)가 없으면 데모 클라이언트(`fixtures`)를 쓴다. 뉴스는 피드를 못 가져오면 예시 데이터로 채우고 `is_demo`로 표시한다(현재 동작 유지).
- XML 필드 후보(`_FIELD_CANDIDATES`)는 Python의 매핑 로직을 그대로 옮긴다.
- 외부 호출에는 연결/읽기 타임아웃을 명시한다.
- Python 버전은 `truststore`로 OS 인증서 저장소를 쓴다. 사내 프록시 인증서(SSL 인스펙션) 환경에서는 JVM 신뢰 저장소(cacerts)에 인증서를 추가해야 할 수 있으며, 이는 배포 문서에 남긴다.

### 5.4 파일 저장

KOSHA 가이드 원문 PDF 수동 첨부는 서버 로컬 폴더(`kosha.guide-files-dir`, 기본 `./kosha_guide_files`)에 저장한다. 업로드는 `multipart/form-data`(`spring.servlet.multipart` 크기 제한 명시).

## 6. 테스트와 검증

| 층 | 방법 |
|---|---|
| 서비스 로직(변경 감지, 태그 매칭, 후보 탐지, 뉴스 보관 정책 등) | JUnit 5. 외부 API는 스텁으로 대체 |
| Mapper SQL | H2(`MODE=Oracle`)로 실행 테스트. **한계**: H2는 Oracle 10g의 실제 문법/제약을 완전히 재현하지 못한다 |
| API 계약 | `MockMvc`로 Python 버전과 동일한 경로/상태 코드/JSON 필드 확인 |
| Oracle 10g 실환경 | **개발 PC에는 10g가 없어 이 작업에서는 검증할 수 없다.** 사내 개발 DB에서 아래 체크리스트를 실행해야 한다 |

Oracle 10g 실환경 체크리스트 (저장소 `docs/oracle10g-checklist.md`에 포함):

1. `schema-oracle10g.sql` 오류 없이 실행되는지
2. `ojdbc6`으로 JDK 17에서 접속되는지, 한글이 깨지지 않는지(DB 문자셋 확인)
3. 모든 Mapper의 `ROWNUM` 페이징과 CLOB `LIKE` 검색 동작
4. 빈 문자열 → NULL 처리 (`app_settings` 포함)
5. 동시 접속 시 시퀀스 채번, 유니크 제약 위반 처리

## 7. 구현 순서 (구현 계획의 뼈대)

1. 프로젝트 골격(Maven, Boot, 프론트엔드 복사, 기본 설정), `/api/health`
2. Oracle 10g 스키마 + 도메인/Mapper (테이블 단위로 TDD)
3. 설정 서비스, 법령 마스터/개정 이력/문서/매핑 API + 동기화 서비스(핵심 기능)
4. 신규 제정 고시 탐지, 본문 캐시, 키워드 검색
5. 뉴스 수집/조회, KOSHA 가이드(동기화, PDF 첨부/텍스트 추출)
6. 스케줄러(일일 유지보수, 따라잡기), Basic 인증
7. 문서 정리(README, 배포/Oracle 체크리스트) 및 불필요 파일 제거

## 8. 열린 항목

| 항목 | 처리 |
|---|---|
| WAR vs 실행 JAR | 담당자 확인 필요. 우선 JAR로 만들고, `SpringBootServletInitializer`는 WAR로 확정될 때 추가한다 |
| Spring Boot `3.5.15` 존재 여부 | 빌드 시 확인 |
| `ojdbc6` 확보 경로 | 사내 저장소 또는 담당자 제공 |
| Oracle 접속 방식(SID/서비스명), DB 문자셋 | 사내 DBA에게 확인 |
| 패키지명 | 사내 규칙 있으면 교체 |
