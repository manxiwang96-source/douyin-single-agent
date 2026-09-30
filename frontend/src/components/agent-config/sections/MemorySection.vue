<template>
  <section class="agent-editor-card agent-memory-section">
    <div class="agent-section-heading">
      <div>
        <h2>记忆</h2>
        <p>长期记忆随当前智能体实例隔离，不在本页新建跨实例记忆商店。</p>
      </div>
    </div>
    <div class="agent-memory-note" data-memory-isolation>
      <p>记住的事实、短期线程和知识检索都限定在当前用户的当前智能体实例内，不会自动带到其它自定义智能体或运营助手。</p>
      <p>正式聊天钉住创建时的 published 配置版本；调试每次重读 draft。本页不提供跨实例记忆开关。</p>
    </div>
  </section>
</template>