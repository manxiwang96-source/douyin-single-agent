<template>
  <section class="agent-editor-card">
    <div class="agent-section-heading">
      <div>
        <h2>审批状态</h2>
        <p>Import、Skill、Script、Tool 四类审批独立显示，互不继承权限。</p>
      </div>
      <button class="agent-btn agent-btn-soft" type="button" @click="emit('refresh')">刷新</button>
    </div>
    <div class="agent-approval-list">
      <div v-for="approval in approvals" :key="approval.approval_id" class="agent-approval-row">
        <span class="agent-approval-kind">{{ APPROVAL_KIND_LABELS[approval.approval_kind] || approval.approval_kind }}</span>
        <strong>{{ approval.resource_code }}</strong>
        <span class="agent-approval-status" :class="`is-${approval.status}`">{{ approvalStatusLabel(approval.status) }}</span>
        <small>{{ approval.reason || "等待当前范围内的用户决策" }}</small>
        <template v-if="approval.status === 'pending'">
          <button class="agent-btn agent-btn-soft" type="button" @click="emit('decide', approval, true)">批准</button>
          <button class="agent-btn agent-btn-ghost" type="button" @click="emit('decide', approval, false)">拒绝</button>
        </template>
      </div>
      <p v-if="!approvals.length" class="agent-side-empty">当前配置版本暂无审批记录。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { ApprovalRecord } from "../../../api/agentConfig";
import { APPROVAL_KIND_LABELS, approvalStatusLabel } from "../../../lib/agentConfig";

defineProps<{
  approvals: ApprovalRecord[];
}>();

const emit = defineEmits<{
  refresh: [];
  decide: [approval: ApprovalRecord, approved: boolean];
}>();
</script>
