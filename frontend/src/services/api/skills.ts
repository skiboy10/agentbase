/**
 * Agent Skills API
 *
 * Read-only access to the Claude Code / agent skills bundled with this
 * Agentbase instance (.claude/skills/*). Used by the Reference → Agent Skills
 * page to let users preview and download a skill for install.
 */

import { apiFetch, API_BASE_URL } from './base';

export interface SkillSummary {
  slug: string;
  name: string;
  description: string;
  files: string[];
  file_count: number;
  size_bytes: number;
}

export interface SkillDetail extends SkillSummary {
  /** Raw SKILL.md markdown, for preview. */
  readme: string;
}

export const skillsApi = {
  list: () => apiFetch<{ skills: SkillSummary[] }>('/api/skills'),

  get: (slug: string) => apiFetch<SkillDetail>(`/api/skills/${slug}`),

  /** Direct URL for the zip archive of a skill (for download links). */
  archiveUrl: (slug: string) => `${API_BASE_URL}/api/skills/${slug}/archive`,
};
