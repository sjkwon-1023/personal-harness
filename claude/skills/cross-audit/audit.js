export const meta = {
  name: 'cross-audit',
  description: 'Large-scope audit with staged verification: parallel discovery, Sonnet cluster screen, escalated two-lens deep verify',
  whenToUse: 'Repo-wide or cross-repo audits (contract mismatches, consistency sweeps) needing adversarially verified findings at controlled cost',
  phases: [
    { title: 'Map', detail: 'per-target recon', model: 'sonnet' },
    { title: 'Find', detail: 'discovery lenses' },
    { title: 'Screen', detail: 'cluster refute', model: 'sonnet' },
    { title: 'Deep-verify', detail: 'escalated findings, refute+repro' },
    { title: 'Gaps', detail: 'completeness critic' },
  ],
}

// ---------- args ----------
// title:       string (선택) — 보고용 제목
// focus:       string (필수) — audit 질문/축. 예: 'App vs backend vs AI module 계약 불일치'
// targets:     [{name, path, hint?}] (필수, 1+) — path 는 절대경로, hint 는 정찰 힌트
// findLenses:  string[] (선택) — 발견 렌즈 문장들. 없으면 pairwise + per-target 기본 렌즈
// finderModel: 'sonnet'|'opus'|'fable' (선택, 기본 'opus')
// clusterSize: number (선택, 기본 6) — Screen 클러스터당 최대 발견 수
// deepCap:     number (선택, 기본 20) — Deep-verify 에 올릴 최대 건수(초과분은 deferred 로 반환, 재라운드용)
const A = args || {}
const targets = A.targets || []
if (!A.focus || !targets.length) throw new Error('cross-audit: args.focus 와 args.targets(1개 이상)가 필요하다')
const FINDER_MODEL = A.finderModel || 'opus'
if (!['sonnet', 'opus', 'fable'].includes(FINDER_MODEL)) throw new Error('cross-audit: finderModel 은 sonnet|opus|fable 중 하나여야 한다')
const CLUSTER_MAX = Math.max(1, Math.floor(A.clusterSize || 6))
const T_LIST = targets.map(t => `- ${t.name}: ${t.path}${t.hint ? ' — ' + t.hint : ''}`).join('\n')

const RO = '너는 read-only 조사 에이전트다. 어떤 파일도 수정·생성·삭제하지 마라. Bash 는 읽기 전용(git/rg/ls 등)으로만 쓴다.'

// ---------- schemas ----------
const MAP_SCHEMA = {
  type: 'object',
  properties: {
    summary: { type: 'string', description: 'focus 관점의 구조 요약 6~12문장' },
    keyFiles: { type: 'array', items: { type: 'string' }, description: '"경로 — 왜 중요한지" 목록' },
  },
  required: ['summary', 'keyFiles'],
}
const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string', description: '한 줄 제목' },
          claim: { type: 'string', description: '주장 전문 — 무엇이 어떻게 어긋나는지' },
          evidence: { type: 'string', description: '근거 file:line 목록 (필수)' },
          severity: { type: 'string', enum: ['low', 'med', 'high'] },
          riskTags: {
            type: 'array',
            items: { type: 'string', enum: ['security', 'cost', 'data-integrity', 'high-complexity'] },
            description: '해당할 때만',
          },
          confidence: { type: 'string', enum: ['low', 'med', 'high'] },
        },
        required: ['title', 'claim', 'evidence', 'severity', 'riskTags', 'confidence'],
      },
    },
  },
  required: ['findings'],
}
const SCREEN_SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: '주장 목록의 id 그대로' },
          verdict: { type: 'string', enum: ['confirmed', 'refuted', 'uncertain'] },
          confidence: { type: 'string', enum: ['low', 'med', 'high'] },
          note: { type: 'string', description: '판정 근거 1~3줄 (반박 시 근거 file:line 포함)' },
        },
        required: ['id', 'verdict', 'confidence', 'note'],
      },
    },
  },
  required: ['verdicts'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    isReal: { type: 'boolean' },
    confidence: { type: 'string', enum: ['low', 'med', 'high'] },
    explanation: { type: 'string' },
    correction: { type: 'string', description: '주장이 부분적으로만 맞으면 정확한 버전' },
  },
  required: ['isReal', 'confidence', 'explanation'],
}

// ---------- Map: 대상별 정찰 (Sonnet) ----------
phase('Map')
const maps = await parallel(targets.map(t => () =>
  agent(
    `${RO}\naudit focus: ${A.focus}\n대상: ${t.name} (${t.path})${t.hint ? '\n힌트: ' + t.hint : ''}\n\n이 대상의 구조를 focus 관점에서 정찰하라: 관련 계약 표면(API·DTO·스키마·설정), 데이터 흐름, focus 판단에 결정적인 파일들. 파일 덤프 말고 요약 + 키 파일 목록만 반환하라.`,
    { label: ('map:' + t.name).slice(0, 48), phase: 'Map', model: 'sonnet', effort: 'medium', schema: MAP_SCHEMA }
  ).then(r => r && ({ ...r, target: t.name }))
))
const mapByName = {}
for (const m of maps.filter(Boolean)) mapByName[m.target] = m
const mapDigest = n => {
  const m = mapByName[n]
  return m ? `[${n}]\n${m.summary}\n키 파일:\n${m.keyFiles.join('\n')}` : `[${n}] (정찰 실패 — 직접 탐색하라)`
}

// ---------- Find: 렌즈별 발견 수집 ----------
phase('Find')
let lenses = A.findLenses
if (!lenses || !lenses.length) {
  lenses = []
  for (let i = 0; i < targets.length; i++) {
    for (let j = i + 1; j < targets.length; j++) {
      lenses.push(`${targets[i].name} ↔ ${targets[j].name}: 두 대상 사이의 계약·데이터 흐름 불일치(요청/응답 스키마, 필드 누락·타입 불일치, 타임아웃·한도 비대칭, 한쪽만 구현된 기능 체인)`)
    }
    lenses.push(`${targets[i].name} 단독: focus 관점의 내부 결함(죽은 계약 필드, 미완성 기능 체인, deprecated 경로 사용, 설정 불일치)`)
  }
}
const findResults = await parallel(lenses.map((lens, i) => () =>
  agent(
    `${RO}\naudit focus: ${A.focus}\n대상 전체:\n${T_LIST}\n\n정찰 요약:\n${targets.map(t => mapDigest(t.name)).join('\n\n')}\n\n너의 발견 렌즈: ${lens}\n\n이 렌즈로 실제 코드를 읽어 발견을 수집하라. 규칙: (1) 모든 발견에 구체 근거 file:line 필수, (2) focus 와 관련된 발견은 발현 확실성과 무관하게 전부 보고하라 — 런타임 발현 판정은 다음 단계(Screen·Deep-verify)의 몫이다. 순수 스타일·네이밍 지적만 제외, (3) 런타임 발현이 불확실하면 버리지 말고 confidence 를 낮게 표시해 보고, (4) riskTags(security/cost/data-integrity/high-complexity)는 해당 시에만.`,
    { label: 'find:' + String(i + 1), phase: 'Find', model: FINDER_MODEL, effort: 'high', schema: FINDINGS_SCHEMA }
  )
))
if (!findResults.filter(Boolean).length) throw new Error('cross-audit: Find 단계 전멸(발견 에이전트 전부 실패) — 결과를 지어내지 않고 중단한다')
const all = []
findResults.filter(Boolean).forEach((r, li) => (r.findings || []).forEach(f => all.push({ ...f, lens: li + 1 })))
const seenKeys = new Set()
const findings = []
for (const f of all) {
  const key = (f.title + '|' + f.evidence).toLowerCase().replace(/\s+/g, ' ').slice(0, 160)
  if (seenKeys.has(key)) continue
  seenKeys.add(key)
  findings.push({ ...f, id: 'f' + (findings.length + 1) })
}
log(`발견 ${all.length}건 수집 → dedup 후 ${findings.length}건`)

// ---------- Screen: 지역성 클러스터 1차 반증 (Sonnet) ----------
phase('Screen')
const groups = {}
for (const f of findings) {
  const m = (f.evidence || '').match(/[\w@.~/-]+?\.[a-z]{2,6}/i)
  const key = m ? m[0].split('/').slice(0, 4).join('/') : 'misc'
  ;(groups[key] = groups[key] || []).push(f)
}
const clusters = []
for (const key of Object.keys(groups)) {
  const g = groups[key]
  for (let i = 0; i < g.length; i += CLUSTER_MAX) clusters.push(g.slice(i, i + CLUSTER_MAX))
}
const screens = await parallel(clusters.map((c, i) => () =>
  agent(
    `${RO}\naudit focus: ${A.focus}\n대상 전체:\n${T_LIST}\n\n아래 주장 목록을 **적대적으로 반증**하라: 각 주장이 못 본 화해 레이어(변환·인터셉터·alias·mapper·설정, 최근 수정 git log)를 실제 코드에서 찾아라. 기준: 런타임에서 실제 발현될 때만 confirmed. 반증 성공 = refuted(반박 근거 file:line 필수), 판단 곤란 = uncertain. verdict 는 주장별로 하나씩 전부 반환하라.\n\n주장 목록:\n${c.map(f => `- id:${f.id} [${f.severity}] ${f.title}\n  주장: ${f.claim}\n  근거: ${f.evidence}`).join('\n')}`,
    { label: 'screen:' + String(i + 1), phase: 'Screen', model: 'sonnet', effort: 'medium', schema: SCREEN_SCHEMA }
  ).then(r => r && ({ clusterIds: c.map(f => f.id), verdicts: r.verdicts || [] }))
))
const screenById = {}
for (const s of screens.filter(Boolean)) {
  const allowed = new Set(s.clusterIds)
  for (const v of s.verdicts) if (allowed.has(v.id)) screenById[v.id] = v
}

// ---------- 에스컬레이션 판정 (순수 코드) ----------
const confirmed = []
const rejected = []
const escalated = []
for (const f of findings) {
  const v = screenById[f.id]
  const needDeep =
    f.severity === 'high' ||
    (f.riskTags || []).length > 0 ||
    !v ||
    v.verdict === 'uncertain' ||
    v.confidence !== 'high' ||
    (v.verdict === 'refuted' && f.confidence === 'high')
  if (needDeep) escalated.push({ ...f, screen: v || null })
  else if (v.verdict === 'confirmed') confirmed.push({ ...f, via: 'screen', screenNote: v.note })
  else rejected.push({ ...f, via: 'screen', screenNote: v.note })
}
if (findings.length && !Object.keys(screenById).length) {
  throw new Error('cross-audit: Screen 단계 전멸(판정 0건) — 전 건 심층행 폭주를 막기 위해 중단한다')
}
const escRatio = findings.length ? escalated.length / findings.length : 0
if (findings.length >= 10 && escRatio > 0.8) {
  log(`경고: 에스컬레이션 비율 ${Math.round(escRatio * 100)}% — Screen 판정 품질 저하 의심(심층 비용 팽창 주의)`)
}
log(`스크린 확정 ${confirmed.length} · 기각 ${rejected.length} · 심층 검증행 ${escalated.length}`)

// ---------- 심층 캡 (결정적 코드) — severity·riskTags·confidence 우선순위 top-N 만 심층행 ----------
const DEEP_CAP = Math.max(1, Math.floor(A.deepCap || 20))
const sevRank = { high: 2, med: 1, low: 0 }
const rank = f => (sevRank[f.severity] || 0) * 100 + (f.riskTags || []).length * 10 + (sevRank[f.confidence] || 0)
escalated.sort((a, b) => rank(b) - rank(a))
const deepTargets = escalated.slice(0, DEEP_CAP)
const deferred = escalated.slice(DEEP_CAP)
if (deferred.length) {
  log(`심층 캡 ${DEEP_CAP} 적용: ${deepTargets.length}건만 심층행, ${deferred.length}건은 deferred 로 반환(검증 안 됨 — 다음 라운드에 재투입할 것)`)
}

// ---------- Deep-verify: 경계선·고위험 건만 2렌즈 ----------
phase('Deep-verify')
const conflicts = []
const deep = await parallel(deepTargets.map(f => () => {
  const base = `audit focus: ${A.focus}\n대상 전체:\n${T_LIST}\n\n주장: ${f.title}\n전문: ${f.claim}\n근거: ${f.evidence}\n1차 스크린 판정: ${f.screen ? f.screen.verdict + ' (' + f.screen.confidence + ') — ' + f.screen.note : '없음'}\n\n관련된 모든 쪽의 실제 코드를 직접 읽어라. isReal=true 는 런타임에서 실제 발현될 때만. 부분적으로만 맞으면 correction 에 정확한 버전을 써라.`
  return parallel([
    () => agent(
      `${RO}\n이 주장을 **반증**하는 게 임무다 — 주장이 못 본 화해 레이어(변환·인터셉터·alias·mapper·설정·최근 수정)를 적극적으로 찾아라. 확실히 반박되면 isReal=false.\n\n${base}`,
      { label: ('refute:' + f.title).slice(0, 48), phase: 'Deep-verify', model: 'opus', effort: 'high', schema: VERDICT_SCHEMA }
    ),
    () => agent(
      `${RO}\n이 주장의 **발현 경로를 재현**하는 게 임무다 — 근거를 따라가 런타임에서 실제로 문제가 드러나는 경로를 코드로 입증하라. 입증에 실패하면 isReal=false.\n\n${base}`,
      { label: ('repro:' + f.title).slice(0, 48), phase: 'Deep-verify', model: 'sonnet', effort: 'high', schema: VERDICT_SCHEMA }
    ),
  ]).then(pair => ({ f, ref: pair[0], rep: pair[1] }))
}))
for (const d of deep.filter(Boolean)) {
  if (d.ref && d.rep && d.ref.isReal === d.rep.isReal) {
    const bucket = d.ref.isReal ? confirmed : rejected
    bucket.push({ ...d.f, via: 'deep', refute: d.ref, repro: d.rep })
  } else {
    conflicts.push({ ...d.f, via: 'deep', refute: d.ref, repro: d.rep })
  }
}

// ---------- Gaps: 완결성 비판 ----------
phase('Gaps')
const gapReport = await agent(
  `${RO}\naudit focus: ${A.focus}\n대상:\n${T_LIST}\n돌린 발견 렌즈:\n${lenses.map((l, i) => (i + 1) + '. ' + l).join('\n')}\n확정 발견 제목:\n${confirmed.map(f => '- ' + f.title).join('\n') || '(없음)'}\n\n완결성 비판: 이 audit 이 놓쳤을 축(안 돈 렌즈, 안 본 모듈, 검증 안 된 가정)을 실제 레포를 근거로 짚어라. 다음 라운드 작업 목록으로 쓸 수 있게 구체적으로.`,
  { label: 'gap-critic', phase: 'Gaps', model: 'opus', effort: 'medium', schema: { type: 'object', properties: { gaps: { type: 'array', items: { type: 'string' } } }, required: ['gaps'] } }
)

return {
  title: A.title || 'cross-audit',
  focus: A.focus,
  stats: { found: all.length, deduped: findings.length, screenClusters: clusters.length, escalated: escalated.length, deepVerified: deepTargets.length, deferred: deferred.length },
  confirmed,
  rejected,
  conflicts,
  deferred,
  gaps: gapReport ? gapReport.gaps : [],
}
