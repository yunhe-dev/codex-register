/**
 * 注册页面 JavaScript
 * 使用 utils.js 中的工具库
 */

// 状态
let currentTask = null;
let currentBatch = null;
let logPollingInterval = null;
let batchPollingInterval = null;
let accountsPollingInterval = null;
let isBatchMode = false;
let isOutlookBatchMode = false;
let outlookAccounts = [];
let taskCompleted = false;  // 标记任务是否已完成
let batchCompleted = false;  // 标记批量任务是否已完成
let taskFinalStatus = null;  // 保存任务的最终状态
let batchFinalStatus = null;  // 保存批量任务的最终状态
let displayedLogs = new Set();  // 用于日志去重
let toastShown = false;  // 标记是否已显示过 toast
let availableServices = {
    tempmail: { available: true, services: [] },
    outlook: { available: false, services: [] },
    moe_mail: { available: false, services: [] },
    temp_mail: { available: false, services: [] },
    duck_mail: { available: false, services: [] },
    freemail: { available: false, services: [] }
};

// WebSocket 相关变量
let webSocket = null;
let batchWebSocket = null;  // 批量任务 WebSocket
let useWebSocket = true;  // 是否使用 WebSocket
let wsHeartbeatInterval = null;  // 心跳定时器
let batchWsHeartbeatInterval = null;  // 批量任务心跳定时器
let activeTaskUuid = null;   // 当前活跃的单任务 UUID（用于页面重新可见时重连）
let activeBatchId = null;    // 当前活跃的批量任务 ID（用于页面重新可见时重连）
let systemLogPollingInterval = null;
let lastSystemLogId = 0;
let backendLogPollingInterval = null;
let lastBackendLogTotalLines = null;
let latestSub2ApiStatus = null;
let currentSub2ApiCheckEnabled = false;
let currentSub2ApiRegisterEnabled = false;
let currentSub2ApiUploadEnabled = true;
let currentSub2ApiUploadServiceIds = [];
let currentSub2ApiRegisterMode = 'parallel';
let currentSub2ApiRegisterConcurrency = 3;
let currentSub2ApiRegisterIntervalMin = 5;
let currentSub2ApiRegisterIntervalMax = 30;
let sub2apiHistoryPollingInterval = null;
let sub2apiHistoryPoints = [];
let sub2apiHistoryRange = '24h';
const sub2apiHistoryVisibleSeries = new Set([
    'accounts_healthy_after_scan',
    'replenish_success_count',
    'accounts_rate_limited_after_scan',
    'accounts_invalid_after_scan',
    'total_accounts_after_scan',
    'total_healthy_after_replenish',
]);
const SUB2API_HISTORY_SERIES = [
    { key: 'accounts_healthy_after_scan', color: '#10a37f' },
    { key: 'replenish_success_count', color: '#2563eb' },
    { key: 'accounts_rate_limited_after_scan', color: '#f59e0b' },
    { key: 'accounts_invalid_after_scan', color: '#ef4444' },
    { key: 'total_accounts_after_scan', color: '#64748b' },
    { key: 'total_healthy_after_replenish', color: '#0ea5e9' },
];
const SUB2API_HISTORY_SERIES_LABELS = {
    accounts_healthy_after_scan: '扫描后健康',
    replenish_success_count: '补货数量',
    accounts_rate_limited_after_scan: '限流数量',
    accounts_invalid_after_scan: '失效数量',
    total_accounts_after_scan: '总账号数量(健康+限流)',
    total_healthy_after_replenish: '补货后总健康',
};
let sub2apiHistoryHoverPoints = [];

// DOM 元素
const elements = {
    form: document.getElementById('registration-form'),
    emailService: document.getElementById('email-service'),
    regMode: document.getElementById('reg-mode'),
    regModeGroup: document.getElementById('reg-mode-group'),
    batchCountGroup: document.getElementById('batch-count-group'),
    batchCount: document.getElementById('batch-count'),
    batchOptions: document.getElementById('batch-options'),
    intervalMin: document.getElementById('interval-min'),
    intervalMax: document.getElementById('interval-max'),
    startBtn: document.getElementById('start-btn'),
    cancelBtn: document.getElementById('cancel-btn'),
    taskStatusRow: document.getElementById('task-status-row'),
    batchProgressSection: document.getElementById('batch-progress-section'),
    consoleLog: document.getElementById('console-log'),
    backendConsoleLog: document.getElementById('backend-console-log'),
    backendLogBody: document.getElementById('backend-log-body'),
    toggleBackendLogBtn: document.getElementById('toggle-backend-log-btn'),
    clearBackendLogBtn: document.getElementById('clear-backend-log-btn'),
    clearLogBtn: document.getElementById('clear-log-btn'),
    // 任务状态
    taskId: document.getElementById('task-id'),
    taskEmail: document.getElementById('task-email'),
    taskStatus: document.getElementById('task-status'),
    taskService: document.getElementById('task-service'),
    taskStatusBadge: document.getElementById('task-status-badge'),
    // 批量状态
    batchProgressText: document.getElementById('batch-progress-text'),
    batchProgressPercent: document.getElementById('batch-progress-percent'),
    progressBar: document.getElementById('progress-bar'),
    batchSuccess: document.getElementById('batch-success'),
    batchFailed: document.getElementById('batch-failed'),
    batchRemaining: document.getElementById('batch-remaining'),
    // 已注册账号
    recentAccountsTable: document.getElementById('recent-accounts-table'),
    refreshAccountsBtn: document.getElementById('refresh-accounts-btn'),
    // Outlook 批量注册
    outlookBatchSection: document.getElementById('outlook-batch-section'),
    outlookAccountsContainer: document.getElementById('outlook-accounts-container'),
    outlookIntervalMin: document.getElementById('outlook-interval-min'),
    outlookIntervalMax: document.getElementById('outlook-interval-max'),
    outlookSkipRegistered: document.getElementById('outlook-skip-registered'),
    outlookConcurrencyMode: document.getElementById('outlook-concurrency-mode'),
    outlookConcurrencyCount: document.getElementById('outlook-concurrency-count'),
    outlookConcurrencyHint: document.getElementById('outlook-concurrency-hint'),
    outlookIntervalGroup: document.getElementById('outlook-interval-group'),
    // 批量并发控件
    concurrencyMode: document.getElementById('concurrency-mode'),
    concurrencyCount: document.getElementById('concurrency-count'),
    concurrencyHint: document.getElementById('concurrency-hint'),
    intervalGroup: document.getElementById('interval-group'),
    // 注册后自动操作
    autoUploadCpa: document.getElementById('auto-upload-cpa'),
    cpaServiceSelectGroup: document.getElementById('cpa-service-select-group'),
    cpaServiceSelect: document.getElementById('cpa-service-select'),
    autoUploadSub2api: document.getElementById('auto-upload-sub2api'),
    sub2apiServiceSelectGroup: document.getElementById('sub2api-service-select-group'),
    sub2apiServiceSelect: document.getElementById('sub2api-service-select'),
    autoUploadTm: document.getElementById('auto-upload-tm'),
    tmServiceSelectGroup: document.getElementById('tm-service-select-group'),
    tmServiceSelect: document.getElementById('tm-service-select'),
    // Sub2API 自动维护
    sub2apiSchedulerStatusBadge: document.getElementById('sub2api-scheduler-status-badge'),
    sub2apiForceCheckBtn: document.getElementById('sub2api-force-check-btn'),
    sub2apiCheckInterval: document.getElementById('sub2api-check-interval'),
    sub2apiCheckSleep: document.getElementById('sub2api-check-sleep'),
    sub2apiRegisterThreshold: document.getElementById('sub2api-register-threshold'),
    sub2apiRegisterBatchCount: document.getElementById('sub2api-register-batch-count'),
    sub2apiRegisterMaxAttempts: document.getElementById('sub2api-register-max-attempts'),
    sub2apiSchedulerEmailService: document.getElementById('sub2api-scheduler-email-service'),
    sub2apiSchedulerAutoUploadSub2api: document.getElementById('sub2api-scheduler-auto-upload-sub2api'),
    sub2apiSchedulerUploadServiceGroup: document.getElementById('sub2api-scheduler-upload-service-group'),
    sub2apiSchedulerUploadService: document.getElementById('sub2api-scheduler-upload-service'),
    sub2apiSchedulerAdvancedToggle: document.getElementById('sub2api-scheduler-advanced-toggle'),
    sub2apiSchedulerAdvancedArrow: document.getElementById('sub2api-scheduler-advanced-arrow'),
    sub2apiSchedulerAdvancedLabel: document.getElementById('sub2api-scheduler-advanced-label'),
    sub2apiSchedulerAdvancedOptions: document.getElementById('sub2api-scheduler-advanced-options'),
    sub2apiSchedulerRegMode: document.getElementById('sub2api-scheduler-reg-mode'),
    sub2apiSchedulerConcurrencyMode: document.getElementById('sub2api-scheduler-concurrency-mode'),
    sub2apiSchedulerConcurrencyCount: document.getElementById('sub2api-scheduler-concurrency-count'),
    sub2apiSchedulerConcurrencyHint: document.getElementById('sub2api-scheduler-concurrency-hint'),
    sub2apiSchedulerIntervalGroup: document.getElementById('sub2api-scheduler-interval-group'),
    sub2apiSchedulerIntervalMin: document.getElementById('sub2api-scheduler-interval-min'),
    sub2apiSchedulerIntervalMax: document.getElementById('sub2api-scheduler-interval-max'),
    sub2apiSaveConfigBtn: document.getElementById('sub2api-save-config-btn'),
    sub2apiStopTaskBtn: document.getElementById('sub2api-stop-task-btn'),
    sub2apiLastScanTime: document.getElementById('sub2api-last-scan-time'),
    sub2apiNextScanTime: document.getElementById('sub2api-next-scan-time'),
    sub2apiLastScanStatus: document.getElementById('sub2api-last-scan-status'),
    sub2apiAccountsScanned: document.getElementById('sub2api-accounts-scanned'),
    sub2apiAccountsHealthy: document.getElementById('sub2api-accounts-healthy'),
    sub2apiAccountsRateLimited: document.getElementById('sub2api-accounts-rate-limited'),
    sub2apiAccountsUnknown: document.getElementById('sub2api-accounts-unknown'),
    sub2apiAccountsInvalid: document.getElementById('sub2api-accounts-invalid'),
    sub2apiAccountsDeleted: document.getElementById('sub2api-accounts-deleted'),
    sub2apiAvailableAccounts: document.getElementById('sub2api-available-accounts'),
    sub2apiLastReplenishTime: document.getElementById('sub2api-last-replenish-time'),
    sub2apiLastReplenishStatus: document.getElementById('sub2api-last-replenish-status'),
    sub2apiReplenishCreatedCount: document.getElementById('sub2api-replenish-created-count'),
    sub2apiReplenishSuccessCount: document.getElementById('sub2api-replenish-success-count'),
    sub2apiReplenishTotalAfter: document.getElementById('sub2api-replenish-total-after'),
    sub2apiHistoryRange: document.getElementById('sub2api-history-range'),
    sub2apiHistoryRefreshBtn: document.getElementById('sub2api-history-refresh-btn'),
    sub2apiHistoryLegend: document.getElementById('sub2api-history-legend'),
    sub2apiHistoryCanvas: document.getElementById('sub2api-history-canvas'),
    sub2apiHistoryEmpty: document.getElementById('sub2api-history-empty'),
    sub2apiHistoryTooltip: document.getElementById('sub2api-history-tooltip'),
};

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
    initEventListeners();
    await Promise.all([
        loadAvailableServices(),
        initAutoUploadOptions(),
    ]);
    populateSub2ApiSchedulerEmailServiceOptions();
    await loadSub2ApiSchedulerConfig();
    await loadSub2ApiSchedulerStatus();
    initSub2ApiHistoryPreferences();
    await loadSub2ApiHistory();
    loadRecentAccounts();
    startAccountsPolling();
    startSub2ApiHistoryPolling();
    initVisibilityReconnect();
    restoreActiveTask();
});

// 初始化注册后自动操作选项（CPA / Sub2API / TM）
async function initAutoUploadOptions() {
    await Promise.all([
        loadServiceSelect('/cpa-services?enabled=true', elements.cpaServiceSelect, elements.autoUploadCpa, elements.cpaServiceSelectGroup),
        loadServiceSelect('/sub2api-services?enabled=true', elements.sub2apiServiceSelect, elements.autoUploadSub2api, elements.sub2apiServiceSelectGroup),
        loadServiceSelect('/tm-services?enabled=true', elements.tmServiceSelect, elements.autoUploadTm, elements.tmServiceSelectGroup),
        loadServiceSelect('/sub2api-services?enabled=true', elements.sub2apiSchedulerUploadService, elements.sub2apiSchedulerAutoUploadSub2api, elements.sub2apiSchedulerUploadServiceGroup),
    ]);
}

// 通用：构建自定义多选下拉组件并处理联动
async function loadServiceSelect(apiPath, container, checkbox, selectGroup) {
    if (!checkbox || !container) return;
    let services = [];
    try {
        services = await api.get(apiPath);
    } catch (e) {}

    if (!services || services.length === 0) {
        checkbox.disabled = true;
        checkbox.title = '请先在设置中添加对应服务';
        const label = checkbox.closest('label');
        if (label) label.style.opacity = '0.5';
        container.innerHTML = '<div class="msd-empty">暂无可用服务</div>';
    } else {
        const items = services.map(s =>
            `<label class="msd-item">
                <input type="checkbox" value="${s.id}" checked>
                <span>${escapeHtml(s.name)}</span>
            </label>`
        ).join('');
        container.innerHTML = `
            <div class="msd-dropdown" id="${container.id}-dd">
                <div class="msd-trigger" onclick="toggleMsd('${container.id}-dd')">
                    <span class="msd-label">全部 (${services.length})</span>
                    <span class="msd-arrow">▼</span>
                </div>
                <div class="msd-list">${items}</div>
            </div>`;
        // 监听 checkbox 变化，更新触发器文字
        container.querySelectorAll('.msd-item input').forEach(cb => {
            cb.addEventListener('change', () => updateMsdLabel(container.id + '-dd'));
        });
        // 点击外部关闭
        document.addEventListener('click', (e) => {
            const dd = document.getElementById(container.id + '-dd');
            if (dd && !dd.contains(e.target)) dd.classList.remove('open');
        }, true);
    }

    // 联动显示/隐藏服务选择区
    checkbox.addEventListener('change', () => {
        if (selectGroup) selectGroup.style.display = checkbox.checked ? 'block' : 'none';
    });
}

function toggleMsd(ddId) {
    const dd = document.getElementById(ddId);
    if (dd) dd.classList.toggle('open');
}

function updateMsdLabel(ddId) {
    const dd = document.getElementById(ddId);
    if (!dd) return;
    const all = dd.querySelectorAll('.msd-item input');
    const checked = dd.querySelectorAll('.msd-item input:checked');
    const label = dd.querySelector('.msd-label');
    if (!label) return;
    if (checked.length === 0) label.textContent = '未选择';
    else if (checked.length === all.length) label.textContent = `全部 (${all.length})`;
    else label.textContent = Array.from(checked).map(c => c.nextElementSibling.textContent).join(', ');
}

// 获取自定义多选下拉中选中的服务 ID 列表
function getSelectedServiceIds(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll('.msd-item input:checked')).map(cb => parseInt(cb.value));
}

function setSelectedServiceIds(container, ids, selectAllWhenEmpty = false) {
    if (!container) return;
    const checkboxes = container.querySelectorAll('.msd-item input');
    if (!checkboxes.length) return;
    const selectedSet = new Set((ids || []).map(v => String(v)));
    const useAll = selectAllWhenEmpty && selectedSet.size === 0;
    checkboxes.forEach(cb => {
        cb.checked = useAll ? true : selectedSet.has(cb.value);
    });
    updateMsdLabel(container.id + '-dd');
}

function setSub2ApiSchedulerAdvancedExpanded(expanded) {
    if (!elements.sub2apiSchedulerAdvancedOptions || !elements.sub2apiSchedulerAdvancedLabel) return;
    elements.sub2apiSchedulerAdvancedOptions.style.display = expanded ? 'block' : 'none';
    elements.sub2apiSchedulerAdvancedLabel.textContent = expanded ? '收起批量高级参数' : '展开批量高级参数';
    if (elements.sub2apiSchedulerAdvancedArrow) {
        elements.sub2apiSchedulerAdvancedArrow.textContent = expanded ? '▾' : '▸';
    }
    try {
        localStorage.setItem('sub2api_scheduler_advanced_expanded', expanded ? '1' : '0');
    } catch (e) {}
}

function toggleSub2ApiSchedulerAdvanced() {
    if (!elements.sub2apiSchedulerAdvancedOptions) return;
    const expanded = elements.sub2apiSchedulerAdvancedOptions.style.display !== 'none';
    setSub2ApiSchedulerAdvancedExpanded(!expanded);
}

function initSub2ApiHistoryPreferences() {
    try {
        const savedRange = localStorage.getItem('sub2api_history_range');
        if (savedRange === '24h' || savedRange === '7d' || savedRange === '30d') {
            sub2apiHistoryRange = savedRange;
        }

        const rawVisible = localStorage.getItem('sub2api_history_visible_series');
        if (rawVisible) {
            const parsed = JSON.parse(rawVisible);
            if (Array.isArray(parsed)) {
                sub2apiHistoryVisibleSeries.clear();
                parsed.forEach(key => {
                    if (typeof key === 'string') {
                        sub2apiHistoryVisibleSeries.add(key);
                    }
                });
                // 老版本没有该曲线配置，升级后默认开启
                if (!sub2apiHistoryVisibleSeries.has('total_accounts_after_scan')) {
                    sub2apiHistoryVisibleSeries.add('total_accounts_after_scan');
                }
            }
        }
    } catch (e) {}

    if (elements.sub2apiHistoryRange) {
        elements.sub2apiHistoryRange.value = sub2apiHistoryRange;
    }
    syncSub2ApiHistoryLegendChecked();
}

function syncSub2ApiHistoryLegendChecked() {
    if (!elements.sub2apiHistoryLegend) return;
    elements.sub2apiHistoryLegend.querySelectorAll('input[type="checkbox"][data-series]').forEach(checkbox => {
        checkbox.checked = sub2apiHistoryVisibleSeries.has(checkbox.dataset.series);
    });
}

// 事件监听
function initEventListeners() {
    // 注册表单提交
    elements.form.addEventListener('submit', handleStartRegistration);

    // 注册模式切换
    elements.regMode.addEventListener('change', handleModeChange);

    // 邮箱服务切换
    elements.emailService.addEventListener('change', handleServiceChange);

    // 取消按钮
    elements.cancelBtn.addEventListener('click', handleCancelTask);

    // 清空日志
    elements.clearLogBtn.addEventListener('click', () => {
        elements.consoleLog.innerHTML = '<div class="log-line info">[系统] 日志已清空</div>';
        displayedLogs.clear();  // 清空日志去重集合
    });
    if (elements.clearBackendLogBtn) {
        elements.clearBackendLogBtn.addEventListener('click', () => {
            if (elements.backendConsoleLog) {
                elements.backendConsoleLog.innerHTML = '<div class="log-line info">[系统] 后台日志已清空</div>';
            }
        });
    }
    if (elements.toggleBackendLogBtn) {
        elements.toggleBackendLogBtn.addEventListener('click', toggleBackendLogPanel);
    }

    // 刷新账号列表
    elements.refreshAccountsBtn.addEventListener('click', () => {
        loadRecentAccounts();
        toast.info('已刷新');
    });

    // 并发模式切换
    elements.concurrencyMode.addEventListener('change', () => {
        handleConcurrencyModeChange(elements.concurrencyMode, elements.concurrencyHint, elements.intervalGroup);
    });
    elements.outlookConcurrencyMode.addEventListener('change', () => {
        handleConcurrencyModeChange(elements.outlookConcurrencyMode, elements.outlookConcurrencyHint, elements.outlookIntervalGroup);
    });
    if (elements.sub2apiSchedulerConcurrencyMode) {
        elements.sub2apiSchedulerConcurrencyMode.addEventListener('change', () => {
            handleConcurrencyModeChange(
                elements.sub2apiSchedulerConcurrencyMode,
                elements.sub2apiSchedulerConcurrencyHint,
                elements.sub2apiSchedulerIntervalGroup,
            );
        });
    }

    if (elements.sub2apiSaveConfigBtn) {
        elements.sub2apiSaveConfigBtn.addEventListener('click', handleSaveSub2ApiSchedulerConfig);
    }
    if (elements.sub2apiStopTaskBtn) {
        elements.sub2apiStopTaskBtn.addEventListener('click', handleStopSub2ApiSchedulerTask);
    }
    if (elements.sub2apiForceCheckBtn) {
        elements.sub2apiForceCheckBtn.addEventListener('click', handleForceCheckSub2Api);
    }
    if (elements.sub2apiSchedulerAdvancedToggle) {
        elements.sub2apiSchedulerAdvancedToggle.addEventListener('click', toggleSub2ApiSchedulerAdvanced);
    }
    if (elements.sub2apiHistoryRange) {
        elements.sub2apiHistoryRange.addEventListener('change', async () => {
            sub2apiHistoryRange = elements.sub2apiHistoryRange.value || '24h';
            try {
                localStorage.setItem('sub2api_history_range', sub2apiHistoryRange);
            } catch (e) {}
            await loadSub2ApiHistory();
        });
    }
    if (elements.sub2apiHistoryRefreshBtn) {
        elements.sub2apiHistoryRefreshBtn.addEventListener('click', async () => {
            await loadSub2ApiHistory();
            toast.info('历史数据已刷新');
        });
    }
    if (elements.sub2apiHistoryLegend) {
        elements.sub2apiHistoryLegend.addEventListener('change', (e) => {
            const target = e.target;
            if (!target || target.tagName !== 'INPUT') return;
            const seriesKey = target.dataset.series;
            if (!seriesKey) return;
            if (target.checked) {
                sub2apiHistoryVisibleSeries.add(seriesKey);
            } else {
                sub2apiHistoryVisibleSeries.delete(seriesKey);
            }
            try {
                localStorage.setItem('sub2api_history_visible_series', JSON.stringify(Array.from(sub2apiHistoryVisibleSeries)));
            } catch (e) {}
            renderSub2ApiHistoryChart();
        });
    }
    if (elements.sub2apiHistoryCanvas) {
        elements.sub2apiHistoryCanvas.addEventListener('mousemove', handleSub2ApiHistoryHoverMove);
        elements.sub2apiHistoryCanvas.addEventListener('mouseleave', hideSub2ApiHistoryTooltip);
    }
    window.addEventListener('resize', debounce(() => {
        renderSub2ApiHistoryChart();
    }, 180));

    let defaultExpanded = false;
    try {
        defaultExpanded = localStorage.getItem('sub2api_scheduler_advanced_expanded') === '1';
    } catch (e) {}
    setSub2ApiSchedulerAdvancedExpanded(defaultExpanded);
    let backendExpanded = true;
    try {
        backendExpanded = localStorage.getItem('backend_log_panel_expanded') !== '0';
    } catch (e) {}
    setBackendLogPanelExpanded(backendExpanded);
    startSystemLogPolling();
    startBackendLogPolling();
}

// 加载可用的邮箱服务
async function loadAvailableServices() {
    try {
        const data = await api.get('/registration/available-services');
        availableServices = data;

        // 更新邮箱服务选择框
        updateEmailServiceOptions();
        populateSub2ApiSchedulerEmailServiceOptions();

        addLog('info', '[系统] 邮箱服务列表已加载');
    } catch (error) {
        console.error('加载邮箱服务列表失败:', error);
        addLog('warning', '[警告] 加载邮箱服务列表失败');
    }
}

// 更新邮箱服务选择框
function updateEmailServiceOptions() {
    const select = elements.emailService;
    select.innerHTML = '';

    // Tempmail
    if (availableServices.tempmail.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = '🌐 临时邮箱';

        availableServices.tempmail.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `tempmail:${service.id || 'default'}`;
            option.textContent = service.name;
            option.dataset.type = 'tempmail';
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    }

    // Outlook
    if (availableServices.outlook.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = `📧 Outlook (${availableServices.outlook.count} 个账户)`;

        availableServices.outlook.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `outlook:${service.id}`;
            option.textContent = service.name + (service.has_oauth ? ' (OAuth)' : '');
            option.dataset.type = 'outlook';
            option.dataset.serviceId = service.id;
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);

        // Outlook 批量注册选项
        const batchOption = document.createElement('option');
        batchOption.value = 'outlook_batch:all';
        batchOption.textContent = `📋 Outlook 批量注册 (${availableServices.outlook.count} 个账户)`;
        batchOption.dataset.type = 'outlook_batch';
        optgroup.appendChild(batchOption);
    } else {
        const optgroup = document.createElement('optgroup');
        optgroup.label = '📧 Outlook (未配置)';

        const option = document.createElement('option');
        option.value = '';
        option.textContent = '请先在邮箱服务页面导入账户';
        option.disabled = true;
        optgroup.appendChild(option);

        select.appendChild(optgroup);
    }

    // 自定义域名
    if (availableServices.moe_mail.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = `🔗 自定义域名 (${availableServices.moe_mail.count} 个服务)`;

        availableServices.moe_mail.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `moe_mail:${service.id || 'default'}`;
            option.textContent = service.name + (service.default_domain ? ` (@${service.default_domain})` : '');
            option.dataset.type = 'moe_mail';
            if (service.id) {
                option.dataset.serviceId = service.id;
            }
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    } else {
        const optgroup = document.createElement('optgroup');
        optgroup.label = '🔗 自定义域名 (未配置)';

        const option = document.createElement('option');
        option.value = '';
        option.textContent = '请先在邮箱服务页面添加服务';
        option.disabled = true;
        optgroup.appendChild(option);

        select.appendChild(optgroup);
    }

    // Temp-Mail（自部署）
    if (availableServices.temp_mail && availableServices.temp_mail.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = `📮 Temp-Mail 自部署 (${availableServices.temp_mail.count} 个服务)`;

        availableServices.temp_mail.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `temp_mail:${service.id}`;
            option.textContent = service.name + (service.domain ? ` (@${service.domain})` : '');
            option.dataset.type = 'temp_mail';
            option.dataset.serviceId = service.id;
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    }

    // DuckMail
    if (availableServices.duck_mail && availableServices.duck_mail.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = `🦆 DuckMail (${availableServices.duck_mail.count} 个服务)`;

        availableServices.duck_mail.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `duck_mail:${service.id}`;
            option.textContent = service.name + (service.default_domain ? ` (@${service.default_domain})` : '');
            option.dataset.type = 'duck_mail';
            option.dataset.serviceId = service.id;
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    }

    // Freemail
    if (availableServices.freemail && availableServices.freemail.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = `📧 Freemail (${availableServices.freemail.count} 个服务)`;

        availableServices.freemail.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `freemail:${service.id}`;
            option.textContent = service.name + (service.domain ? ` (@${service.domain})` : '');
            option.dataset.type = 'freemail';
            option.dataset.serviceId = service.id;
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    }
}

function populateSub2ApiSchedulerEmailServiceOptions(selectedValue = '') {
    const select = elements.sub2apiSchedulerEmailService;
    if (!select) return;

    const preservedValue = selectedValue || select.value || 'tempmail:default';
    select.innerHTML = '';

    const appendGroup = (label, services, valueBuilder, textBuilder) => {
        if (!services || services.length === 0) return;
        const optgroup = document.createElement('optgroup');
        optgroup.label = label;
        services.forEach(service => {
            const option = document.createElement('option');
            option.value = valueBuilder(service);
            option.textContent = textBuilder(service);
            optgroup.appendChild(option);
        });
        select.appendChild(optgroup);
    };

    appendGroup('🌐 临时邮箱', availableServices.tempmail?.services || [], service => `tempmail:${service.id || 'default'}`, service => service.name);
    appendGroup('📧 Outlook', availableServices.outlook?.services || [], service => `outlook:${service.id}`, service => service.name + (service.has_oauth ? ' (OAuth)' : ''));
    appendGroup('🔗 自定义域名', availableServices.moe_mail?.services || [], service => `moe_mail:${service.id || 'default'}`, service => service.name + (service.default_domain ? ` (@${service.default_domain})` : ''));
    appendGroup('📮 Temp-Mail 自部署', availableServices.temp_mail?.services || [], service => `temp_mail:${service.id}`, service => service.name + (service.domain ? ` (@${service.domain})` : ''));
    appendGroup('🦆 DuckMail', availableServices.duck_mail?.services || [], service => `duck_mail:${service.id}`, service => service.name + (service.default_domain ? ` (@${service.default_domain})` : ''));
    appendGroup('📧 Freemail', availableServices.freemail?.services || [], service => `freemail:${service.id}`, service => service.name + (service.domain ? ` (@${service.domain})` : ''));

    if (!select.options.length) {
        const option = document.createElement('option');
        option.value = 'tempmail:default';
        option.textContent = 'Tempmail.lol';
        select.appendChild(option);
    }

    const hasPreservedOption = Array.from(select.options).some(option => option.value === preservedValue);
    if (!hasPreservedOption && preservedValue) {
        const option = document.createElement('option');
        option.value = preservedValue;
        option.textContent = `已保存服务 (${preservedValue})`;
        select.appendChild(option);
    }

    select.value = preservedValue;
}

async function loadSub2ApiSchedulerConfig() {
    if (!elements.sub2apiCheckInterval) return;

    try {
        const config = await api.get('/sub2api-scheduler/config');
        currentSub2ApiCheckEnabled = !!config.check_enabled;
        currentSub2ApiRegisterEnabled = !!config.register_enabled;
        currentSub2ApiUploadEnabled = config.upload_enabled !== false;
        currentSub2ApiUploadServiceIds = Array.isArray(config.upload_service_ids) ? config.upload_service_ids : [];
        currentSub2ApiRegisterMode = (config.register_mode === 'pipeline' || config.register_mode === 'parallel')
            ? config.register_mode
            : 'parallel';
        currentSub2ApiRegisterConcurrency = parseInt(config.register_concurrency) || 3;
        currentSub2ApiRegisterIntervalMin = parseInt(config.register_interval_min);
        if (Number.isNaN(currentSub2ApiRegisterIntervalMin)) currentSub2ApiRegisterIntervalMin = 5;
        currentSub2ApiRegisterIntervalMax = parseInt(config.register_interval_max);
        if (Number.isNaN(currentSub2ApiRegisterIntervalMax)) currentSub2ApiRegisterIntervalMax = 30;
        currentSub2ApiRegisterIntervalMax = Math.max(currentSub2ApiRegisterIntervalMin, currentSub2ApiRegisterIntervalMax);

        elements.sub2apiCheckInterval.value = config.check_interval ?? 60;
        elements.sub2apiCheckSleep.value = config.check_sleep ?? 1;
        elements.sub2apiRegisterThreshold.value = config.register_threshold ?? 10;
        elements.sub2apiRegisterBatchCount.value = config.register_batch_count ?? 5;
        elements.sub2apiRegisterMaxAttempts.value = config.register_max_attempts ?? 10;
        if (elements.sub2apiSchedulerAutoUploadSub2api) {
            elements.sub2apiSchedulerAutoUploadSub2api.checked = currentSub2ApiUploadEnabled;
        }
        if (elements.sub2apiSchedulerUploadServiceGroup) {
            elements.sub2apiSchedulerUploadServiceGroup.style.display = currentSub2ApiUploadEnabled ? 'block' : 'none';
        }
        setSelectedServiceIds(elements.sub2apiSchedulerUploadService, currentSub2ApiUploadServiceIds, true);
        if (elements.sub2apiSchedulerConcurrencyMode) {
            elements.sub2apiSchedulerConcurrencyMode.value = currentSub2ApiRegisterMode;
            handleConcurrencyModeChange(
                elements.sub2apiSchedulerConcurrencyMode,
                elements.sub2apiSchedulerConcurrencyHint,
                elements.sub2apiSchedulerIntervalGroup,
            );
        }
        if (elements.sub2apiSchedulerConcurrencyCount) {
            elements.sub2apiSchedulerConcurrencyCount.value = currentSub2ApiRegisterConcurrency;
        }
        if (elements.sub2apiSchedulerIntervalMin) {
            elements.sub2apiSchedulerIntervalMin.value = currentSub2ApiRegisterIntervalMin;
        }
        if (elements.sub2apiSchedulerIntervalMax) {
            elements.sub2apiSchedulerIntervalMax.value = currentSub2ApiRegisterIntervalMax;
        }
        populateSub2ApiSchedulerEmailServiceOptions(config.email_service || 'tempmail:default');
        updateSub2ApiSchedulerBadge(currentSub2ApiCheckEnabled);
    } catch (error) {
        console.error('加载 Sub2API 调度配置失败', error);
        addLog('warning', '[警告] 加载 Sub2API 自动维护配置失败');
    }
}

function formatDateTime(value) {
    if (!value) return '-';
    const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN', {
        hour12: false,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    });
}

function updateSub2ApiSchedulerSummary(status) {
    if (!status) return;
    latestSub2ApiStatus = status;
    currentSub2ApiCheckEnabled = !!status.check_enabled;
    if (elements.sub2apiForceCheckBtn) {
        const isRunning = !!status.is_running;
        elements.sub2apiForceCheckBtn.textContent = isRunning ? '停止扫描' : '立即扫描';
        elements.sub2apiForceCheckBtn.classList.toggle('btn-primary', !isRunning);
        elements.sub2apiForceCheckBtn.classList.toggle('btn-danger', isRunning);
    }
    if (elements.sub2apiStopTaskBtn) {
        const isEnabled = !!status.check_enabled;
        elements.sub2apiStopTaskBtn.textContent = isEnabled ? '停止自动任务' : '开始自动任务';
        elements.sub2apiStopTaskBtn.classList.toggle('btn-primary', !isEnabled);
        elements.sub2apiStopTaskBtn.classList.toggle('btn-danger', isEnabled);
    }
    if (elements.sub2apiLastScanTime) {
        elements.sub2apiLastScanTime.textContent = formatDateTime(status.last_scan_finished_at || status.last_scan_started_at);
    }
    if (elements.sub2apiNextScanTime) {
        let nextScanText = '-';
        if (status.check_enabled) {
            if (status.next_scan_scheduled_at) {
                nextScanText = formatDateTime(status.next_scan_scheduled_at);
            } else if (status.is_running) {
                nextScanText = '待本轮完成';
            } else {
                nextScanText = '等待调度';
            }
        }
        elements.sub2apiNextScanTime.textContent = nextScanText;
    }
    if (elements.sub2apiLastScanStatus) {
        const statusMap = {
            idle: '待机',
            running: '扫描中',
            completed: '已完成',
            failed: '失败',
            cancelled: '已停止',
        };
        elements.sub2apiLastScanStatus.textContent = statusMap[status.last_scan_status] || status.last_scan_status || '-';
    }
    if (elements.sub2apiAccountsScanned) {
        elements.sub2apiAccountsScanned.textContent = String(status.accounts_scanned ?? 0);
    }
    if (elements.sub2apiAccountsHealthy) {
        elements.sub2apiAccountsHealthy.textContent = String(status.accounts_healthy ?? 0);
    }
    if (elements.sub2apiAccountsRateLimited) {
        elements.sub2apiAccountsRateLimited.textContent = String(status.accounts_rate_limited ?? 0);
    }
    if (elements.sub2apiAccountsUnknown) {
        elements.sub2apiAccountsUnknown.textContent = String(status.accounts_unknown ?? 0);
    }
    if (elements.sub2apiAccountsInvalid) {
        elements.sub2apiAccountsInvalid.textContent = String(status.accounts_invalid ?? 0);
    }
    if (elements.sub2apiAccountsDeleted) {
        elements.sub2apiAccountsDeleted.textContent = String(status.accounts_deleted ?? 0);
    }
    if (elements.sub2apiAvailableAccounts) {
        elements.sub2apiAvailableAccounts.textContent = String(status.available_accounts ?? 0);
    }
    if (elements.sub2apiLastReplenishTime) {
        elements.sub2apiLastReplenishTime.textContent = formatDateTime(status.last_replenish_finished_at || status.last_replenish_started_at);
    }
    if (elements.sub2apiLastReplenishStatus) {
        const replenishStatusMap = {
            idle: '待机',
            running: '补货中',
            completed: '已完成',
            partial: '部分完成',
            failed: '失败',
        };
        elements.sub2apiLastReplenishStatus.textContent =
            replenishStatusMap[status.last_replenish_status] || status.last_replenish_status || '-';
    }
    if (elements.sub2apiReplenishCreatedCount) {
        elements.sub2apiReplenishCreatedCount.textContent = String(status.last_replenish_created_count ?? 0);
    }
    if (elements.sub2apiReplenishSuccessCount) {
        elements.sub2apiReplenishSuccessCount.textContent = String(status.last_replenish_success_count ?? 0);
    }
    if (elements.sub2apiReplenishTotalAfter) {
        elements.sub2apiReplenishTotalAfter.textContent = String(status.last_replenish_total_after ?? 0);
    }
}

async function loadSub2ApiSchedulerStatus() {
    try {
        const res = await api.get('/sub2api-scheduler/status');
        if (res && res.success) {
            updateSub2ApiSchedulerSummary(res.status);
        }
    } catch (error) {
        console.error('加载 Sub2API 调度状态失败', error);
    }
}

async function loadSub2ApiHistory() {
    if (!elements.sub2apiHistoryCanvas) return;
    try {
        const res = await api.get(`/sub2api-scheduler/history?range=${encodeURIComponent(sub2apiHistoryRange)}&limit=1200`);
        if (!res || res.success === false) {
            sub2apiHistoryPoints = [];
            renderSub2ApiHistoryChart();
            return;
        }
        sub2apiHistoryPoints = Array.isArray(res.points) ? res.points : [];
        renderSub2ApiHistoryChart();
    } catch (error) {
        console.error('加载 Sub2API 历史走势失败', error);
        sub2apiHistoryPoints = [];
        renderSub2ApiHistoryChart();
    }
}

function startSub2ApiHistoryPolling() {
    if (sub2apiHistoryPollingInterval) return;
    sub2apiHistoryPollingInterval = setInterval(() => {
        loadSub2ApiHistory();
    }, 15000);
}

function _parseHistoryPointTime(rawValue) {
    if (!rawValue || typeof rawValue !== 'string') return null;
    const value = rawValue.endsWith('Z') ? rawValue : `${rawValue}Z`;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return date;
}

function _formatHistoryAxisTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN', {
        hour12: false,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function _formatHistoryTooltipTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('zh-CN', {
        hour12: false,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    });
}

function _getHistoryEventLabel(eventType) {
    const map = {
        scan_completed: '扫描完成',
        replenish_round_completed: '补货轮次完成',
        replenish_completed: '补货完成',
        auto_task_completed: '自动任务完成',
    };
    return map[eventType] || eventType || '-';
}

function hideSub2ApiHistoryTooltip() {
    if (elements.sub2apiHistoryTooltip) {
        elements.sub2apiHistoryTooltip.style.display = 'none';
    }
}

function handleSub2ApiHistoryHoverMove(event) {
    if (!elements.sub2apiHistoryCanvas || !elements.sub2apiHistoryTooltip || !sub2apiHistoryHoverPoints.length) return;
    const rect = elements.sub2apiHistoryCanvas.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;

    let nearest = sub2apiHistoryHoverPoints[0];
    let minDistance = Math.abs(localX - nearest.x);
    for (let i = 1; i < sub2apiHistoryHoverPoints.length; i += 1) {
        const candidate = sub2apiHistoryHoverPoints[i];
        const dist = Math.abs(localX - candidate.x);
        if (dist < minDistance) {
            minDistance = dist;
            nearest = candidate;
        }
    }

    if (!nearest || minDistance > 24) {
        hideSub2ApiHistoryTooltip();
        return;
    }

    const activeSeries = SUB2API_HISTORY_SERIES.filter(series => sub2apiHistoryVisibleSeries.has(series.key));
    const valueLines = activeSeries
        .map(series => {
            const value = nearest.point[series.key];
            if (!Number.isFinite(value)) return '';
            const label = SUB2API_HISTORY_SERIES_LABELS[series.key] || series.key;
            return `${label}: ${value}`;
        })
        .filter(Boolean);

    elements.sub2apiHistoryTooltip.innerHTML = `
        <div>${_formatHistoryTooltipTime(nearest.time)}</div>
        <div>事件: ${_getHistoryEventLabel(nearest.point.event_type)}</div>
        ${valueLines.map(line => `<div>${line}</div>`).join('')}
    `;
    elements.sub2apiHistoryTooltip.style.display = 'block';

    const tip = elements.sub2apiHistoryTooltip;
    const tipWidth = tip.offsetWidth || 220;
    const tipHeight = tip.offsetHeight || 80;
    const left = Math.min(Math.max(8, localX + 12), rect.width - tipWidth - 8);
    const top = Math.min(Math.max(8, localY - tipHeight - 8), rect.height - tipHeight - 8);
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
}

function renderSub2ApiHistoryChart() {
    const canvas = elements.sub2apiHistoryCanvas;
    if (!canvas) return;

    const historyKeys = SUB2API_HISTORY_SERIES.map(series => series.key);
    const points = (sub2apiHistoryPoints || [])
        .map(point => {
            const normalized = { ...point, __date: _parseHistoryPointTime(point.timestamp) };
            historyKeys.forEach(key => {
                const value = normalized[key];
                normalized[key] = Number.isFinite(value) ? value : 0;
            });
            return normalized;
        })
        .filter(point => point.__date)
        .sort((a, b) => a.__date.getTime() - b.__date.getTime());

    const hasData = points.length > 0;
    if (elements.sub2apiHistoryEmpty) {
        elements.sub2apiHistoryEmpty.style.display = hasData ? 'none' : 'flex';
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.clientWidth || 720;
    const height = canvas.clientHeight || 260;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.clearRect(0, 0, width, height);

    if (!hasData) {
        sub2apiHistoryHoverPoints = [];
        hideSub2ApiHistoryTooltip();
        return;
    }

    const padding = { top: 14, right: 16, bottom: 36, left: 42 };
    const chartWidth = Math.max(10, width - padding.left - padding.right);
    const chartHeight = Math.max(10, height - padding.top - padding.bottom);
    const xMinRaw = points[0].__date.getTime();
    const xMaxRaw = points[points.length - 1].__date.getTime();
    const baseSpan = Math.max(1, xMaxRaw - xMinRaw);
    const sidePaddingMs = Math.max(30000, Math.floor(baseSpan * 0.08));
    const xMin = xMinRaw - sidePaddingMs;
    const xMax = xMaxRaw + sidePaddingMs;
    const safeSpan = Math.max(1, xMax - xMin);

    const activeSeries = SUB2API_HISTORY_SERIES.filter(series => sub2apiHistoryVisibleSeries.has(series.key));
    const allValues = [];
    activeSeries.forEach(series => {
        points.forEach(point => {
            const value = point[series.key];
            if (Number.isFinite(value)) {
                allValues.push(value);
            }
        });
    });
    const yMaxBase = allValues.length ? Math.max(...allValues) : 0;
    const yMax = Math.max(10, Math.ceil((yMaxBase * 1.15) / 5) * 5);
    const yMin = 0;

    const xToCanvas = x => padding.left + ((x - xMin) / safeSpan) * chartWidth;
    const yToCanvas = y => padding.top + (1 - (y - yMin) / Math.max(1, yMax - yMin)) * chartHeight;

    ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
        const yValue = yMin + ((yMax - yMin) * i) / 4;
        const y = yToCanvas(yValue);
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();
    }

    ctx.fillStyle = 'rgba(100, 116, 139, 0.9)';
    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let i = 0; i <= 4; i += 1) {
        const yValue = yMin + ((yMax - yMin) * i) / 4;
        const y = yToCanvas(yValue);
        ctx.fillText(String(Math.round(yValue)), padding.left - 6, y);
    }

    const rawSpan = Math.max(0, xMaxRaw - xMinRaw);
    const xTicks = rawSpan === 0
        ? [xMinRaw]
        : [xMinRaw, xMinRaw + rawSpan / 2, xMaxRaw];
    ctx.textBaseline = 'top';
    xTicks.forEach((tick, index) => {
        const x = xToCanvas(tick);
        if (xTicks.length === 1) ctx.textAlign = 'center';
        else if (index === 0) ctx.textAlign = 'left';
        else if (index === xTicks.length - 1) ctx.textAlign = 'right';
        else ctx.textAlign = 'center';
        ctx.fillText(_formatHistoryAxisTime(tick), x, height - padding.bottom + 8);
    });

    sub2apiHistoryHoverPoints = points.map(point => ({
        x: xToCanvas(point.__date.getTime()),
        time: point.__date.getTime(),
        point,
    }));

    activeSeries.forEach(series => {
        ctx.strokeStyle = series.color;
        ctx.lineWidth = 2;
        ctx.beginPath();

        let drawing = false;
        points.forEach(point => {
            const value = point[series.key];
            if (!Number.isFinite(value)) {
                drawing = false;
                return;
            }
            const x = xToCanvas(point.__date.getTime());
            const y = yToCanvas(value);
            if (!drawing) {
                ctx.moveTo(x, y);
                drawing = true;
            } else {
                ctx.lineTo(x, y);
            }
        });
        ctx.stroke();

        points.forEach(point => {
            const value = point[series.key];
            if (!Number.isFinite(value)) return;
            const x = xToCanvas(point.__date.getTime());
            const y = yToCanvas(value);
            ctx.fillStyle = series.color;
            ctx.beginPath();
            ctx.arc(x, y, 2.5, 0, Math.PI * 2);
            ctx.fill();
        });
    });
}

async function handleSaveSub2ApiSchedulerConfig() {
    elements.sub2apiSaveConfigBtn.disabled = true;
    elements.sub2apiSaveConfigBtn.textContent = '保存中...';
    currentSub2ApiUploadEnabled = elements.sub2apiSchedulerAutoUploadSub2api
        ? elements.sub2apiSchedulerAutoUploadSub2api.checked
        : true;
    currentSub2ApiUploadServiceIds = currentSub2ApiUploadEnabled
        ? getSelectedServiceIds(elements.sub2apiSchedulerUploadService)
        : [];
    currentSub2ApiRegisterMode = elements.sub2apiSchedulerConcurrencyMode
        ? elements.sub2apiSchedulerConcurrencyMode.value
        : 'parallel';
    if (currentSub2ApiRegisterMode !== 'pipeline') currentSub2ApiRegisterMode = 'parallel';
    currentSub2ApiRegisterConcurrency = Math.max(1, parseInt(elements.sub2apiSchedulerConcurrencyCount?.value) || 3);
    currentSub2ApiRegisterIntervalMin = Math.max(0, parseInt(elements.sub2apiSchedulerIntervalMin?.value) || 5);
    currentSub2ApiRegisterIntervalMax = Math.max(
        currentSub2ApiRegisterIntervalMin,
        parseInt(elements.sub2apiSchedulerIntervalMax?.value) || 30,
    );

    try {
        await api.post('/sub2api-scheduler/config', {
            check_enabled: currentSub2ApiCheckEnabled,
            check_interval: parseInt(elements.sub2apiCheckInterval.value) || 60,
            check_sleep: parseInt(elements.sub2apiCheckSleep.value) || 0,
            register_enabled: currentSub2ApiRegisterEnabled,
            register_threshold: parseInt(elements.sub2apiRegisterThreshold.value) || 10,
            register_batch_count: parseInt(elements.sub2apiRegisterBatchCount.value) || 5,
            register_max_attempts: parseInt(elements.sub2apiRegisterMaxAttempts.value) || 10,
            email_service: elements.sub2apiSchedulerEmailService ? elements.sub2apiSchedulerEmailService.value : 'tempmail:default',
            upload_enabled: currentSub2ApiUploadEnabled,
            upload_service_ids: currentSub2ApiUploadServiceIds,
            register_mode: currentSub2ApiRegisterMode,
            register_concurrency: currentSub2ApiRegisterConcurrency,
            register_interval_min: currentSub2ApiRegisterIntervalMin,
            register_interval_max: currentSub2ApiRegisterIntervalMax,
        });
        updateSub2ApiSchedulerBadge(currentSub2ApiCheckEnabled);
        await loadSub2ApiSchedulerStatus();
        toast.success('Sub2API 自动维护配置已保存');
        addLog('success', '[系统] Sub2API 自动维护与补注册配置已保存');
    } catch (error) {
        toast.error(`保存失败: ${error.message}`);
        addLog('error', `[错误] 保存 Sub2API 自动维护配置失败: ${error.message}`);
    } finally {
        elements.sub2apiSaveConfigBtn.disabled = false;
        elements.sub2apiSaveConfigBtn.textContent = '保存并应用配置';
    }
}

async function handleStopSub2ApiSchedulerTask() {
    elements.sub2apiStopTaskBtn.disabled = true;
    const nextCheckEnabled = !currentSub2ApiCheckEnabled;
    const nextRegisterEnabled = nextCheckEnabled ? true : false;
    currentSub2ApiUploadEnabled = elements.sub2apiSchedulerAutoUploadSub2api
        ? elements.sub2apiSchedulerAutoUploadSub2api.checked
        : true;
    currentSub2ApiUploadServiceIds = currentSub2ApiUploadEnabled
        ? getSelectedServiceIds(elements.sub2apiSchedulerUploadService)
        : [];
    currentSub2ApiRegisterMode = elements.sub2apiSchedulerConcurrencyMode
        ? elements.sub2apiSchedulerConcurrencyMode.value
        : 'parallel';
    if (currentSub2ApiRegisterMode !== 'pipeline') currentSub2ApiRegisterMode = 'parallel';
    currentSub2ApiRegisterConcurrency = Math.max(1, parseInt(elements.sub2apiSchedulerConcurrencyCount?.value) || 3);
    currentSub2ApiRegisterIntervalMin = Math.max(0, parseInt(elements.sub2apiSchedulerIntervalMin?.value) || 5);
    currentSub2ApiRegisterIntervalMax = Math.max(
        currentSub2ApiRegisterIntervalMin,
        parseInt(elements.sub2apiSchedulerIntervalMax?.value) || 30,
    );

    try {
        await api.post('/sub2api-scheduler/config', {
            check_enabled: nextCheckEnabled,
            check_interval: parseInt(elements.sub2apiCheckInterval.value) || 60,
            check_sleep: parseInt(elements.sub2apiCheckSleep.value) || 0,
            register_enabled: nextRegisterEnabled,
            register_threshold: parseInt(elements.sub2apiRegisterThreshold.value) || 10,
            register_batch_count: parseInt(elements.sub2apiRegisterBatchCount.value) || 5,
            register_max_attempts: parseInt(elements.sub2apiRegisterMaxAttempts.value) || 10,
            email_service: elements.sub2apiSchedulerEmailService ? elements.sub2apiSchedulerEmailService.value : 'tempmail:default',
            upload_enabled: currentSub2ApiUploadEnabled,
            upload_service_ids: currentSub2ApiUploadServiceIds,
            register_mode: currentSub2ApiRegisterMode,
            register_concurrency: currentSub2ApiRegisterConcurrency,
            register_interval_min: currentSub2ApiRegisterIntervalMin,
            register_interval_max: currentSub2ApiRegisterIntervalMax,
        });
        currentSub2ApiCheckEnabled = nextCheckEnabled;
        currentSub2ApiRegisterEnabled = nextRegisterEnabled;
        updateSub2ApiSchedulerBadge(nextCheckEnabled);
        await loadSub2ApiSchedulerStatus();
        if (nextCheckEnabled) {
            toast.success('已开始自动任务');
            addLog('success', '[系统] 已开启 Sub2API 自动维护与补注册');
        } else {
            toast.info('已停止 Sub2API 自动任务');
            addLog('warning', '[系统] 已关闭 Sub2API 自动维护与补注册');
        }
    } catch (error) {
        toast.error(`切换失败: ${error.message}`);
        addLog('error', `[错误] 切换 Sub2API 自动任务失败: ${error.message}`);
    } finally {
        elements.sub2apiStopTaskBtn.disabled = false;
    }
}

async function handleForceCheckSub2Api() {
    elements.sub2apiForceCheckBtn.disabled = true;
    const isRunning = !!(latestSub2ApiStatus && latestSub2ApiStatus.is_running);

    try {
        if (isRunning) {
            const res = await api.post('/sub2api-scheduler/stop-scan');
            if (res.success) {
                toast.info(res.message || '已请求停止扫描');
                addLog('warning', '[系统] 已请求停止当前 Sub2API 扫描');
            } else {
                toast.warning(res.message || '当前没有进行中的扫描任务');
            }
        } else {
            addLog('info', '[系统] 正在启动 Sub2API 扫描...');
            const res = await api.post('/sub2api-scheduler/trigger');
            if (res.success) {
                toast.success(res.message || '已开始扫描');
            } else {
                toast.warning(res.message || '当前已有扫描任务在运行');
            }
        }
        await loadSub2ApiSchedulerStatus();
    } catch (error) {
        toast.error(`操作失败: ${error.message}`);
        addLog('error', `[错误] Sub2API 扫描操作失败: ${error.message}`);
    } finally {
        elements.sub2apiForceCheckBtn.disabled = false;
    }
}

function updateSub2ApiSchedulerBadge(isEnabled) {
    const badge = elements.sub2apiSchedulerStatusBadge;
    if (!badge) return;

    if (isEnabled) {
        badge.textContent = '已开启';
        badge.style.backgroundColor = 'rgba(76, 175, 80, 0.1)';
        badge.style.color = 'var(--success-color)';
    } else {
        badge.textContent = '未开启';
        badge.style.backgroundColor = 'rgba(244, 67, 54, 0.1)';
        badge.style.color = 'var(--error-color)';
    }
}

function startSystemLogPolling() {
    if (systemLogPollingInterval) return;

    systemLogPollingInterval = setInterval(async () => {
        try {
            const res = await api.get(`/sub2api-scheduler/logs?since_id=${lastSystemLogId}`);
            if (res && Array.isArray(res.logs) && res.logs.length > 0) {
                res.logs.forEach(log => {
                    addLog(log.level || 'info', log.msg || '');
                });
                lastSystemLogId = res.last_id;
            }
            await loadSub2ApiSchedulerStatus();
        } catch (error) {
            console.error('轮询 Sub2API 系统日志失败', error);
        }
    }, 5000);
}

// 处理邮箱服务切换
function handleServiceChange(e) {
    const value = e.target.value;
    if (!value) return;

    const [type, id] = value.split(':');
    // 处理 Outlook 批量注册模式
    if (type === 'outlook_batch') {
        isOutlookBatchMode = true;
        elements.outlookBatchSection.style.display = 'block';
        elements.regModeGroup.style.display = 'none';
        elements.batchCountGroup.style.display = 'none';
        elements.batchOptions.style.display = 'none';
        loadOutlookAccounts();
        addLog('info', '[系统] 已切换到 Outlook 批量注册模式');
        return;
    } else {
        isOutlookBatchMode = false;
        elements.outlookBatchSection.style.display = 'none';
        elements.regModeGroup.style.display = 'block';
    }

    // 显示服务信息
    if (type === 'outlook') {
        const service = availableServices.outlook.services.find(s => s.id == id);
        if (service) {
            addLog('info', `[系统] 已选择 Outlook 账户: ${service.name}`);
        }
    } else if (type === 'moe_mail') {
        const service = availableServices.moe_mail.services.find(s => s.id == id);
        if (service) {
            addLog('info', `[系统] 已选择自定义域名服务: ${service.name}`);
        }
    } else if (type === 'temp_mail') {
        const service = availableServices.temp_mail.services.find(s => s.id == id);
        if (service) {
            addLog('info', `[系统] 已选择 Temp-Mail 自部署服务: ${service.name}`);
        }
    } else if (type === 'duck_mail') {
        const service = availableServices.duck_mail.services.find(s => s.id == id);
        if (service) {
            addLog('info', `[系统] 已选择 DuckMail 服务: ${service.name}`);
        }
    } else if (type === 'freemail') {
        const service = availableServices.freemail.services.find(s => s.id == id);
        if (service) {
            addLog('info', `[系统] 已选择 Freemail 服务: ${service.name}`);
        }
    }
}

// 模式切换
function handleModeChange(e) {
    const mode = e.target.value;
    isBatchMode = mode === 'batch';

    elements.batchCountGroup.style.display = isBatchMode ? 'block' : 'none';
    elements.batchOptions.style.display = isBatchMode ? 'block' : 'none';
}

// 并发模式切换（批量）
function handleConcurrencyModeChange(selectEl, hintEl, intervalGroupEl) {
    const mode = selectEl.value;
    if (mode === 'parallel') {
        hintEl.textContent = '所有任务分成 N 个并发批次同时执行';
        intervalGroupEl.style.display = 'none';
    } else {
        hintEl.textContent = '同时最多运行 N 个任务，每隔 interval 秒启动新任务';
        intervalGroupEl.style.display = 'block';
    }
}

// 开始注册
async function handleStartRegistration(e) {
    e.preventDefault();

    const selectedValue = elements.emailService.value;
    if (!selectedValue) {
        toast.error('请选择一个邮箱服务');
        return;
    }

    // 处理 Outlook 批量注册模式
    if (isOutlookBatchMode) {
        await handleOutlookBatchRegistration();
        return;
    }

    const [emailServiceType, serviceId] = selectedValue.split(':');

    // 禁用开始按钮
    elements.startBtn.disabled = true;
    elements.cancelBtn.disabled = false;

    // 清空日志
    elements.consoleLog.innerHTML = '';

    // 构建请求数据（代理从设置中自动获取）
    const requestData = {
        email_service_type: emailServiceType,
        auto_upload_cpa: elements.autoUploadCpa ? elements.autoUploadCpa.checked : false,
        cpa_service_ids: elements.autoUploadCpa && elements.autoUploadCpa.checked ? getSelectedServiceIds(elements.cpaServiceSelect) : [],
        auto_upload_sub2api: elements.autoUploadSub2api ? elements.autoUploadSub2api.checked : false,
        sub2api_service_ids: elements.autoUploadSub2api && elements.autoUploadSub2api.checked ? getSelectedServiceIds(elements.sub2apiServiceSelect) : [],
        auto_upload_tm: elements.autoUploadTm ? elements.autoUploadTm.checked : false,
        tm_service_ids: elements.autoUploadTm && elements.autoUploadTm.checked ? getSelectedServiceIds(elements.tmServiceSelect) : [],
    };

    // 如果选择了数据库中的服务，传递 service_id
    if (serviceId && serviceId !== 'default') {
        requestData.email_service_id = parseInt(serviceId);
    }

    if (isBatchMode) {
        await handleBatchRegistration(requestData);
    } else {
        await handleSingleRegistration(requestData);
    }
}

// 单次注册
async function handleSingleRegistration(requestData) {
    // 重置任务状态
    taskCompleted = false;
    taskFinalStatus = null;
    displayedLogs.clear();  // 清空日志去重集合
    toastShown = false;  // 重置 toast 标志

    addLog('info', '[系统] 正在启动注册任务...');

    try {
        const data = await api.post('/registration/start', requestData);

        currentTask = data;
        activeTaskUuid = data.task_uuid;  // 保存用于重连
        // 持久化到 sessionStorage，跨页面导航后可恢复
        sessionStorage.setItem('activeTask', JSON.stringify({ task_uuid: data.task_uuid, mode: 'single' }));
        addLog('info', `[系统] 任务已创建: ${data.task_uuid}`);
        showTaskStatus(data);
        updateTaskStatus('running');

        // 优先使用 WebSocket
        connectWebSocket(data.task_uuid);

    } catch (error) {
        addLog('error', `[错误] 启动失败: ${error.message}`);
        toast.error(error.message);
        resetButtons();
    }
}


// ============== WebSocket 功能 ==============

// 连接 WebSocket
function connectWebSocket(taskUuid) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/task/${taskUuid}`;

    try {
        webSocket = new WebSocket(wsUrl);

        webSocket.onopen = () => {
            console.log('WebSocket 连接成功');
            useWebSocket = true;
            // 停止轮询（如果有）
            stopLogPolling();
            // 开始心跳
            startWebSocketHeartbeat();
        };

        webSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'log') {
                const logType = getLogType(data.message);
                addLog(logType, data.message);
            } else if (data.type === 'status') {
                if (data.email) {
                    elements.taskEmail.textContent = data.email;
                }
                if (data.email_service) {
                    elements.taskService.textContent = getServiceTypeText(data.email_service);
                }
                updateTaskStatus(data.status);

                // 检查是否完成
                if (['completed', 'failed', 'cancelled', 'cancelling'].includes(data.status)) {
                    // 保存最终状态，用于 onclose 判断
                    taskFinalStatus = data.status;
                    taskCompleted = true;

                    // 断开 WebSocket（异步操作）
                    disconnectWebSocket();

                    // 任务完成后再重置按钮
                    resetButtons();

                    // 只显示一次 toast
                    if (!toastShown) {
                        toastShown = true;
                        if (data.status === 'completed') {
                            addLog('success', '[成功] 注册成功！');
                            toast.success('注册成功！');
                            // 刷新账号列表
                            loadRecentAccounts();
                        } else if (data.status === 'failed') {
                            addLog('error', '[错误] 注册失败');
                            toast.error('注册失败');
                        } else if (data.status === 'cancelled' || data.status === 'cancelling') {
                            addLog('warning', '[警告] 任务已取消');
                        }
                    }
                }
            } else if (data.type === 'pong') {
                // 心跳响应，忽略
            }
        };

        webSocket.onclose = (event) => {
            console.log('WebSocket 连接关闭:', event.code);
            stopWebSocketHeartbeat();

            // 只有在任务未完成且最终状态不是完成状态时才切换到轮询
            // 使用 taskFinalStatus 而不是 currentTask.status，因为 currentTask 可能已被重置
            const shouldPoll = !taskCompleted &&
                               taskFinalStatus === null;  // 如果 taskFinalStatus 有值，说明任务已完成

            if (shouldPoll && currentTask) {
                console.log('切换到轮询模式');
                useWebSocket = false;
                startLogPolling(currentTask.task_uuid);
            }
        };

        webSocket.onerror = (error) => {
            console.error('WebSocket 错误:', error);
            // 切换到轮询
            useWebSocket = false;
            stopWebSocketHeartbeat();
            startLogPolling(taskUuid);
        };

    } catch (error) {
        console.error('WebSocket 连接失败:', error);
        useWebSocket = false;
        startLogPolling(taskUuid);
    }
}

// 断开 WebSocket
function disconnectWebSocket() {
    stopWebSocketHeartbeat();
    if (webSocket) {
        webSocket.close();
        webSocket = null;
    }
}

// 开始心跳
function startWebSocketHeartbeat() {
    stopWebSocketHeartbeat();
    wsHeartbeatInterval = setInterval(() => {
        if (webSocket && webSocket.readyState === WebSocket.OPEN) {
            webSocket.send(JSON.stringify({ type: 'ping' }));
        }
    }, 25000);  // 每 25 秒发送一次心跳
}

// 停止心跳
function stopWebSocketHeartbeat() {
    if (wsHeartbeatInterval) {
        clearInterval(wsHeartbeatInterval);
        wsHeartbeatInterval = null;
    }
}

// 发送取消请求
function cancelViaWebSocket() {
    if (webSocket && webSocket.readyState === WebSocket.OPEN) {
        webSocket.send(JSON.stringify({ type: 'cancel' }));
    }
}

// 批量注册
async function handleBatchRegistration(requestData) {
    // 重置批量任务状态
    batchCompleted = false;
    batchFinalStatus = null;
    displayedLogs.clear();  // 清空日志去重集合
    toastShown = false;  // 重置 toast 标志

    const count = parseInt(elements.batchCount.value) || 5;
    const intervalMin = parseInt(elements.intervalMin.value) || 5;
    const intervalMax = parseInt(elements.intervalMax.value) || 30;
    const concurrency = parseInt(elements.concurrencyCount.value) || 3;
    const mode = elements.concurrencyMode.value || 'pipeline';

    requestData.count = count;
    requestData.interval_min = intervalMin;
    requestData.interval_max = intervalMax;
    requestData.concurrency = Math.min(50, Math.max(1, concurrency));
    requestData.mode = mode;

    addLog('info', `[系统] 正在启动批量注册任务 (数量: ${count})...`);

    try {
        const data = await api.post('/registration/batch', requestData);

        currentBatch = data;
        activeBatchId = data.batch_id;  // 保存用于重连
        // 持久化到 sessionStorage，跨页面导航后可恢复
        sessionStorage.setItem('activeTask', JSON.stringify({ batch_id: data.batch_id, mode: 'batch', total: data.count }));
        addLog('info', `[系统] 批量任务已创建: ${data.batch_id}`);
        addLog('info', `[系统] 共 ${data.count} 个任务已加入队列`);
        showBatchStatus(data);

        // 优先使用 WebSocket
        connectBatchWebSocket(data.batch_id);

    } catch (error) {
        addLog('error', `[错误] 启动失败: ${error.message}`);
        toast.error(error.message);
        resetButtons();
    }
}

// 取消任务
async function handleCancelTask() {
    // 禁用取消按钮，防止重复点击
    elements.cancelBtn.disabled = true;
    addLog('info', '[系统] 正在提交取消请求...');

    try {
        // 批量任务取消（包括普通批量模式和 Outlook 批量模式）
        if (currentBatch && (isBatchMode || isOutlookBatchMode)) {
            // 优先通过 WebSocket 取消
            if (batchWebSocket && batchWebSocket.readyState === WebSocket.OPEN) {
                batchWebSocket.send(JSON.stringify({ type: 'cancel' }));
                addLog('warning', '[警告] 批量任务取消请求已提交');
                toast.info('任务取消请求已提交');
            } else {
                // 降级到 REST API
                const endpoint = isOutlookBatchMode
                    ? `/registration/outlook-batch/${currentBatch.batch_id}/cancel`
                    : `/registration/batch/${currentBatch.batch_id}/cancel`;

                await api.post(endpoint);
                addLog('warning', '[警告] 批量任务取消请求已提交');
                toast.info('任务取消请求已提交');
                stopBatchPolling();
                resetButtons();
            }
        }
        // 单次任务取消
        else if (currentTask) {
            // 优先通过 WebSocket 取消
            if (webSocket && webSocket.readyState === WebSocket.OPEN) {
                webSocket.send(JSON.stringify({ type: 'cancel' }));
                addLog('warning', '[警告] 任务取消请求已提交');
                toast.info('任务取消请求已提交');
            } else {
                // 降级到 REST API
                await api.post(`/registration/tasks/${currentTask.task_uuid}/cancel`);
                addLog('warning', '[警告] 任务已取消');
                toast.info('任务已取消');
                stopLogPolling();
                resetButtons();
            }
        }
        // 没有活动任务
        else {
            addLog('warning', '[警告] 没有活动的任务可以取消');
            toast.warning('没有活动的任务');
            resetButtons();
        }
    } catch (error) {
        addLog('error', `[错误] 取消失败: ${error.message}`);
        toast.error(error.message);
        // 恢复取消按钮，允许重试
        elements.cancelBtn.disabled = false;
    }
}

// 开始轮询日志
function startLogPolling(taskUuid) {
    let lastLogIndex = 0;

    logPollingInterval = setInterval(async () => {
        try {
            const data = await api.get(`/registration/tasks/${taskUuid}/logs`);

            // 更新任务状态
            updateTaskStatus(data.status);

            // 更新邮箱信息
            if (data.email) {
                elements.taskEmail.textContent = data.email;
            }
            if (data.email_service) {
                elements.taskService.textContent = getServiceTypeText(data.email_service);
            }

            // 添加新日志
            const logs = data.logs || [];
            for (let i = lastLogIndex; i < logs.length; i++) {
                const log = logs[i];
                const logType = getLogType(log);
                addLog(logType, log);
            }
            lastLogIndex = logs.length;

            // 检查任务是否完成
            if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                stopLogPolling();
                resetButtons();

                // 只显示一次 toast
                if (!toastShown) {
                    toastShown = true;
                    if (data.status === 'completed') {
                        addLog('success', '[成功] 注册成功！');
                        toast.success('注册成功！');
                        // 刷新账号列表
                        loadRecentAccounts();
                    } else if (data.status === 'failed') {
                        addLog('error', '[错误] 注册失败');
                        toast.error('注册失败');
                    } else if (data.status === 'cancelled') {
                        addLog('warning', '[警告] 任务已取消');
                    }
                }
            }
        } catch (error) {
            console.error('轮询日志失败:', error);
        }
    }, 1000);
}

// 停止轮询日志
function stopLogPolling() {
    if (logPollingInterval) {
        clearInterval(logPollingInterval);
        logPollingInterval = null;
    }
}

// 开始轮询批量状态
function startBatchPolling(batchId) {
    batchPollingInterval = setInterval(async () => {
        try {
            const data = await api.get(`/registration/batch/${batchId}`);
            updateBatchProgress(data);

            // 检查是否完成
            if (data.finished) {
                stopBatchPolling();
                resetButtons();

                // 只显示一次 toast
                if (!toastShown) {
                    toastShown = true;
                    addLog('info', `[完成] 批量任务完成！成功: ${data.success}, 失败: ${data.failed}`);
                    if (data.success > 0) {
                        toast.success(`批量注册完成，成功 ${data.success} 个`);
                        // 刷新账号列表
                        loadRecentAccounts();
                    } else {
                        toast.warning('批量注册完成，但没有成功注册任何账号');
                    }
                }
            }
        } catch (error) {
            console.error('轮询批量状态失败:', error);
        }
    }, 2000);
}

// 停止轮询批量状态
function stopBatchPolling() {
    if (batchPollingInterval) {
        clearInterval(batchPollingInterval);
        batchPollingInterval = null;
    }
}

// 显示任务状态
function showTaskStatus(task) {
    elements.taskStatusRow.style.display = 'grid';
    elements.batchProgressSection.style.display = 'none';
    elements.taskStatusBadge.style.display = 'inline-flex';
    elements.taskId.textContent = task.task_uuid.substring(0, 8) + '...';
    elements.taskEmail.textContent = '-';
    elements.taskService.textContent = '-';
}

// 更新任务状态
function updateTaskStatus(status) {
    const statusInfo = {
        pending: { text: '等待中', class: 'pending' },
        running: { text: '运行中', class: 'running' },
        completed: { text: '已完成', class: 'completed' },
        failed: { text: '失败', class: 'failed' },
        cancelled: { text: '已取消', class: 'disabled' }
    };

    const info = statusInfo[status] || { text: status, class: '' };
    elements.taskStatusBadge.textContent = info.text;
    elements.taskStatusBadge.className = `status-badge ${info.class}`;
    elements.taskStatus.textContent = info.text;
}

// 显示批量状态
function showBatchStatus(batch) {
    elements.batchProgressSection.style.display = 'block';
    elements.taskStatusRow.style.display = 'none';
    elements.taskStatusBadge.style.display = 'none';
    elements.batchProgressText.textContent = `0/${batch.count}`;
    elements.batchProgressPercent.textContent = '0%';
    elements.progressBar.style.width = '0%';
    elements.batchSuccess.textContent = '0';
    elements.batchFailed.textContent = '0';
    elements.batchRemaining.textContent = batch.count;

    // 重置计数器
    elements.batchSuccess.dataset.last = '0';
    elements.batchFailed.dataset.last = '0';
}

// 更新批量进度
function updateBatchProgress(data) {
    const progress = ((data.completed / data.total) * 100).toFixed(0);
    elements.batchProgressText.textContent = `${data.completed}/${data.total}`;
    elements.batchProgressPercent.textContent = `${progress}%`;
    elements.progressBar.style.width = `${progress}%`;
    elements.batchSuccess.textContent = data.success;
    elements.batchFailed.textContent = data.failed;
    elements.batchRemaining.textContent = data.total - data.completed;

    // 记录日志（避免重复）
    if (data.completed > 0) {
        const lastSuccess = parseInt(elements.batchSuccess.dataset.last || '0');
        const lastFailed = parseInt(elements.batchFailed.dataset.last || '0');

        if (data.success > lastSuccess) {
            addLog('success', `[成功] 第 ${data.success} 个账号注册成功`);
        }
        if (data.failed > lastFailed) {
            addLog('error', `[失败] 第 ${data.failed} 个账号注册失败`);
        }

        elements.batchSuccess.dataset.last = data.success;
        elements.batchFailed.dataset.last = data.failed;
    }
}

// 加载最近注册的账号
async function loadRecentAccounts() {
    try {
        const data = await api.get('/accounts?page=1&page_size=10');

        if (data.accounts.length === 0) {
            elements.recentAccountsTable.innerHTML = `
                <tr>
                    <td colspan="5">
                        <div class="empty-state" style="padding: var(--spacing-md);">
                            <div class="empty-state-icon">📭</div>
                            <div class="empty-state-title">暂无已注册账号</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        elements.recentAccountsTable.innerHTML = data.accounts.map(account => `
            <tr data-id="${account.id}">
                <td>${account.id}</td>
                <td>
                    <span style="display:inline-flex;align-items:center;gap:4px;">
                        <span title="${escapeHtml(account.email)}">${escapeHtml(account.email)}</span>
                        <button class="btn-copy-icon copy-email-btn" data-email="${escapeHtml(account.email)}" title="复制邮箱">📋</button>
                    </span>
                </td>
                <td class="password-cell">
                    ${account.password
                        ? `<span style="display:inline-flex;align-items:center;gap:4px;">
                            <span class="password-hidden" title="点击查看">${escapeHtml(account.password.substring(0, 8))}...</span>
                            <button class="btn-copy-icon copy-pwd-btn" data-pwd="${escapeHtml(account.password)}" title="复制密码">📋</button>
                           </span>`
                        : '-'}
                </td>
                <td>
                    ${getStatusIcon(account.status)}
                </td>
            </tr>
        `).join('');

        // 绑定复制按钮事件
        elements.recentAccountsTable.querySelectorAll('.copy-email-btn').forEach(btn => {
            btn.addEventListener('click', (e) => { e.stopPropagation(); copyToClipboard(btn.dataset.email); });
        });
        elements.recentAccountsTable.querySelectorAll('.copy-pwd-btn').forEach(btn => {
            btn.addEventListener('click', (e) => { e.stopPropagation(); copyToClipboard(btn.dataset.pwd); });
        });

    } catch (error) {
        console.error('加载账号列表失败:', error);
    }
}

// 开始账号列表轮询
function startAccountsPolling() {
    // 每30秒刷新一次账号列表
    accountsPollingInterval = setInterval(() => {
        loadRecentAccounts();
    }, 30000);
}

// 添加日志
function addLog(type, message) {
    // 日志去重：使用消息内容的 hash 作为键
    const logKey = `${type}:${message}`;
    if (displayedLogs.has(logKey)) {
        return;  // 已经显示过，跳过
    }
    displayedLogs.add(logKey);

    // 限制去重集合大小，避免内存泄漏
    if (displayedLogs.size > 1000) {
        // 清空一半的记录
        const keys = Array.from(displayedLogs);
        keys.slice(0, 500).forEach(k => displayedLogs.delete(k));
    }

    const line = document.createElement('div');
    line.className = `log-line ${type}`;

    // 添加时间戳
    const timestamp = new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    line.innerHTML = `<span class="timestamp">[${timestamp}]</span>${escapeHtml(message)}`;
    elements.consoleLog.appendChild(line);

    // 自动滚动到底部
    elements.consoleLog.scrollTop = elements.consoleLog.scrollHeight;

    // 限制日志行数
    const lines = elements.consoleLog.querySelectorAll('.log-line');
    if (lines.length > 500) {
        lines[0].remove();
    }
}

function addBackendLog(type, message) {
    if (!elements.backendConsoleLog) return;
    const line = document.createElement('div');
    line.className = `log-line ${type || 'info'}`;
    line.textContent = message || '';
    elements.backendConsoleLog.appendChild(line);
    elements.backendConsoleLog.scrollTop = elements.backendConsoleLog.scrollHeight;

    const lines = elements.backendConsoleLog.querySelectorAll('.log-line');
    if (lines.length > 800) {
        lines[0].remove();
    }
}

function getBackendLogType(line) {
    if (typeof line !== 'string') return 'info';
    const lowerLine = line.toLowerCase();
    if (lowerLine.includes('error') || lowerLine.includes('[error]') || lowerLine.includes('失败') || lowerLine.includes('错误')) {
        return 'error';
    }
    if (lowerLine.includes('warning') || lowerLine.includes('[warning]') || lowerLine.includes('警告') || lowerLine.includes('限流')) {
        return 'warning';
    }
    if (lowerLine.includes('success') || lowerLine.includes('[success]') || lowerLine.includes('完成') || lowerLine.includes('正常')) {
        return 'success';
    }
    if (lowerLine.includes('debug') || lowerLine.includes('[debug]')) {
        return 'debug';
    }
    return 'info';
}

function replaceBackendLogs(lines) {
    if (!elements.backendConsoleLog) return;
    elements.backendConsoleLog.innerHTML = '';
    (lines || []).forEach(line => addBackendLog(getBackendLogType(line), line));
}

async function fetchBackendLogs() {
    try {
        const res = await api.get('/settings/logs?lines=400');
        if (!res || !Array.isArray(res.logs)) return;

        const totalLines = Number.isFinite(res.total_lines) ? res.total_lines : res.logs.length;
        if (lastBackendLogTotalLines === null || totalLines < lastBackendLogTotalLines) {
            // 初次加载，或日志文件轮转/重置时，直接重绘最近日志
            replaceBackendLogs(res.logs);
            lastBackendLogTotalLines = totalLines;
            return;
        }

        const delta = totalLines - lastBackendLogTotalLines;
        if (delta <= 0) return;

        if (delta >= res.logs.length) {
            // 增量超过当前窗口，直接重绘窗口，避免漏行
            replaceBackendLogs(res.logs);
        } else {
            const newLines = res.logs.slice(-delta);
            newLines.forEach(line => addBackendLog(getBackendLogType(line), line));
        }

        lastBackendLogTotalLines = totalLines;
    } catch (error) {
        console.error('轮询后端日志失败', error);
    }
}

function startBackendLogPolling() {
    if (backendLogPollingInterval) return;
    fetchBackendLogs();
    backendLogPollingInterval = setInterval(fetchBackendLogs, 5000);
}

function setBackendLogPanelExpanded(expanded) {
    if (!elements.backendLogBody || !elements.toggleBackendLogBtn) return;
    elements.backendLogBody.style.display = expanded ? 'block' : 'none';
    elements.toggleBackendLogBtn.textContent = expanded ? '▾' : '▸';
    elements.toggleBackendLogBtn.title = expanded ? '折叠' : '展开';
    try {
        localStorage.setItem('backend_log_panel_expanded', expanded ? '1' : '0');
    } catch (e) {}
}

function toggleBackendLogPanel() {
    if (!elements.backendLogBody) return;
    const expanded = elements.backendLogBody.style.display !== 'none';
    setBackendLogPanelExpanded(!expanded);
}

// 获取日志类型
function getLogType(log) {
    if (typeof log !== 'string') return 'info';

    const lowerLog = log.toLowerCase();
    if (lowerLog.includes('error') || lowerLog.includes('失败') || lowerLog.includes('错误')) {
        return 'error';
    }
    if (lowerLog.includes('warning') || lowerLog.includes('警告')) {
        return 'warning';
    }
    if (lowerLog.includes('success') || lowerLog.includes('成功') || lowerLog.includes('完成')) {
        return 'success';
    }
    return 'info';
}

// 重置按钮状态
function resetButtons() {
    elements.startBtn.disabled = false;
    elements.cancelBtn.disabled = true;
    currentTask = null;
    currentBatch = null;
    // 重置完成标志
    taskCompleted = false;
    batchCompleted = false;
    // 重置最终状态标志
    taskFinalStatus = null;
    batchFinalStatus = null;
    // 清除活跃任务标识
    activeTaskUuid = null;
    activeBatchId = null;
    // 清除 sessionStorage 持久化状态
    sessionStorage.removeItem('activeTask');
    // 断开 WebSocket
    disconnectWebSocket();
    disconnectBatchWebSocket();
    // 注意：不重置 isOutlookBatchMode，因为用户可能想继续使用 Outlook 批量模式
}

// HTML 转义
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// ============== Outlook 批量注册功能 ==============

// 加载 Outlook 账户列表
async function loadOutlookAccounts() {
    try {
        elements.outlookAccountsContainer.innerHTML = '<div class="loading-placeholder" style="text-align: center; padding: var(--spacing-md); color: var(--text-muted);">加载中...</div>';

        const data = await api.get('/registration/outlook-accounts');
        outlookAccounts = data.accounts || [];

        renderOutlookAccountsList();

        addLog('info', `[系统] 已加载 ${data.total} 个 Outlook 账户 (已注册: ${data.registered_count}, 未注册: ${data.unregistered_count})`);

    } catch (error) {
        console.error('加载 Outlook 账户列表失败:', error);
        elements.outlookAccountsContainer.innerHTML = `<div style="text-align: center; padding: var(--spacing-md); color: var(--text-muted);">加载失败: ${error.message}</div>`;
        addLog('error', `[错误] 加载 Outlook 账户列表失败: ${error.message}`);
    }
}

// 渲染 Outlook 账户列表
function renderOutlookAccountsList() {
    if (outlookAccounts.length === 0) {
        elements.outlookAccountsContainer.innerHTML = '<div style="text-align: center; padding: var(--spacing-md); color: var(--text-muted);">没有可用的 Outlook 账户</div>';
        return;
    }

    const html = outlookAccounts.map(account => `
        <label class="outlook-account-item" style="display: flex; align-items: center; padding: var(--spacing-sm); border-bottom: 1px solid var(--border-light); cursor: pointer; ${account.is_registered ? 'opacity: 0.6;' : ''}" data-id="${account.id}" data-registered="${account.is_registered}">
            <input type="checkbox" class="outlook-account-checkbox" value="${account.id}" ${account.is_registered ? '' : 'checked'} style="margin-right: var(--spacing-sm);">
            <div style="flex: 1;">
                <div style="font-weight: 500;">${escapeHtml(account.email)}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">
                    ${account.is_registered
                        ? `<span style="color: var(--success-color);">✓ 已注册</span>`
                        : '<span style="color: var(--primary-color);">未注册</span>'
                    }
                    ${account.has_oauth ? ' | OAuth' : ''}
                </div>
            </div>
        </label>
    `).join('');

    elements.outlookAccountsContainer.innerHTML = html;
}

// 全选
function selectAllOutlookAccounts() {
    const checkboxes = document.querySelectorAll('.outlook-account-checkbox');
    checkboxes.forEach(cb => cb.checked = true);
}

// 只选未注册
function selectUnregisteredOutlook() {
    const items = document.querySelectorAll('.outlook-account-item');
    items.forEach(item => {
        const checkbox = item.querySelector('.outlook-account-checkbox');
        const isRegistered = item.dataset.registered === 'true';
        checkbox.checked = !isRegistered;
    });
}

// 取消全选
function deselectAllOutlookAccounts() {
    const checkboxes = document.querySelectorAll('.outlook-account-checkbox');
    checkboxes.forEach(cb => cb.checked = false);
}

// 处理 Outlook 批量注册
async function handleOutlookBatchRegistration() {
    // 重置批量任务状态
    batchCompleted = false;
    batchFinalStatus = null;
    displayedLogs.clear();  // 清空日志去重集合
    toastShown = false;  // 重置 toast 标志

    // 获取选中的账户
    const selectedIds = [];
    document.querySelectorAll('.outlook-account-checkbox:checked').forEach(cb => {
        selectedIds.push(parseInt(cb.value));
    });

    if (selectedIds.length === 0) {
        toast.error('请选择至少一个 Outlook 账户');
        return;
    }

    const intervalMin = parseInt(elements.outlookIntervalMin.value) || 5;
    const intervalMax = parseInt(elements.outlookIntervalMax.value) || 30;
    const skipRegistered = elements.outlookSkipRegistered.checked;
    const concurrency = parseInt(elements.outlookConcurrencyCount.value) || 3;
    const mode = elements.outlookConcurrencyMode.value || 'pipeline';

    // 禁用开始按钮
    elements.startBtn.disabled = true;
    elements.cancelBtn.disabled = false;

    // 清空日志
    elements.consoleLog.innerHTML = '';

    const requestData = {
        service_ids: selectedIds,
        skip_registered: skipRegistered,
        interval_min: intervalMin,
        interval_max: intervalMax,
        concurrency: Math.min(50, Math.max(1, concurrency)),
        mode: mode,
        auto_upload_cpa: elements.autoUploadCpa ? elements.autoUploadCpa.checked : false,
        cpa_service_ids: elements.autoUploadCpa && elements.autoUploadCpa.checked ? getSelectedServiceIds(elements.cpaServiceSelect) : [],
        auto_upload_sub2api: elements.autoUploadSub2api ? elements.autoUploadSub2api.checked : false,
        sub2api_service_ids: elements.autoUploadSub2api && elements.autoUploadSub2api.checked ? getSelectedServiceIds(elements.sub2apiServiceSelect) : [],
        auto_upload_tm: elements.autoUploadTm ? elements.autoUploadTm.checked : false,
        tm_service_ids: elements.autoUploadTm && elements.autoUploadTm.checked ? getSelectedServiceIds(elements.tmServiceSelect) : [],
    };

    addLog('info', `[系统] 正在启动 Outlook 批量注册 (${selectedIds.length} 个账户)...`);

    try {
        const data = await api.post('/registration/outlook-batch', requestData);

        if (data.to_register === 0) {
            addLog('warning', '[警告] 所有选中的邮箱都已注册，无需重复注册');
            toast.warning('所有选中的邮箱都已注册');
            resetButtons();
            return;
        }

        currentBatch = { batch_id: data.batch_id, ...data };
        activeBatchId = data.batch_id;  // 保存用于重连
        // 持久化到 sessionStorage，跨页面导航后可恢复
        sessionStorage.setItem('activeTask', JSON.stringify({ batch_id: data.batch_id, mode: isOutlookBatchMode ? 'outlook_batch' : 'batch', total: data.to_register }));
        addLog('info', `[系统] 批量任务已创建: ${data.batch_id}`);
        addLog('info', `[系统] 总数: ${data.total}, 跳过已注册: ${data.skipped}, 待注册: ${data.to_register}`);

        // 初始化批量状态显示
        showBatchStatus({ count: data.to_register });

        // 优先使用 WebSocket
        connectBatchWebSocket(data.batch_id);

    } catch (error) {
        addLog('error', `[错误] 启动失败: ${error.message}`);
        toast.error(error.message);
        resetButtons();
    }
}

// ============== 批量任务 WebSocket 功能 ==============

// 连接批量任务 WebSocket
function connectBatchWebSocket(batchId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/batch/${batchId}`;

    try {
        batchWebSocket = new WebSocket(wsUrl);

        batchWebSocket.onopen = () => {
            console.log('批量任务 WebSocket 连接成功');
            // 停止轮询（如果有）
            stopBatchPolling();
            // 开始心跳
            startBatchWebSocketHeartbeat();
        };

        batchWebSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'log') {
                const logType = getLogType(data.message);
                addLog(logType, data.message);
            } else if (data.type === 'status') {
                // 更新进度
                if (data.total !== undefined) {
                    updateBatchProgress({
                        total: data.total,
                        completed: data.completed || 0,
                        success: data.success || 0,
                        failed: data.failed || 0
                    });
                }

                // 检查是否完成
                if (['completed', 'failed', 'cancelled', 'cancelling'].includes(data.status)) {
                    // 保存最终状态，用于 onclose 判断
                    batchFinalStatus = data.status;
                    batchCompleted = true;

                    // 断开 WebSocket（异步操作）
                    disconnectBatchWebSocket();

                    // 任务完成后再重置按钮
                    resetButtons();

                    // 只显示一次 toast
                    if (!toastShown) {
                        toastShown = true;
                        if (data.status === 'completed') {
                            const batchLabel = isOutlookBatchMode ? 'Outlook 批量' : '批量';
                            addLog('success', `[完成] ${batchLabel}任务完成！成功: ${data.success}, 失败: ${data.failed}, 跳过: ${data.skipped || 0}`);
                            if (data.success > 0) {
                                toast.success(`${batchLabel}注册完成，成功 ${data.success} 个`);
                                loadRecentAccounts();
                            } else {
                                toast.warning(`${batchLabel}注册完成，但没有成功注册任何账号`);
                            }
                        } else if (data.status === 'failed') {
                            addLog('error', '[错误] 批量任务执行失败');
                            toast.error('批量任务执行失败');
                        } else if (data.status === 'cancelled' || data.status === 'cancelling') {
                            addLog('warning', '[警告] 批量任务已取消');
                        }
                    }
                }
            } else if (data.type === 'pong') {
                // 心跳响应，忽略
            }
        };

        batchWebSocket.onclose = (event) => {
            console.log('批量任务 WebSocket 连接关闭:', event.code);
            stopBatchWebSocketHeartbeat();

            // 只有在任务未完成且最终状态不是完成状态时才切换到轮询
            // 使用 batchFinalStatus 而不是 currentBatch.status，因为 currentBatch 可能已被重置
            const shouldPoll = !batchCompleted &&
                               batchFinalStatus === null;  // 如果 batchFinalStatus 有值，说明任务已完成

            if (shouldPoll && currentBatch) {
                console.log('切换到轮询模式');
                startCurrentBatchPolling(currentBatch.batch_id);
            }
        };

        batchWebSocket.onerror = (error) => {
            console.error('批量任务 WebSocket 错误:', error);
            stopBatchWebSocketHeartbeat();
            // 切换到轮询
            startCurrentBatchPolling(batchId);
        };

    } catch (error) {
        console.error('批量任务 WebSocket 连接失败:', error);
        startCurrentBatchPolling(batchId);
    }
}

// 断开批量任务 WebSocket
function disconnectBatchWebSocket() {
    stopBatchWebSocketHeartbeat();
    if (batchWebSocket) {
        batchWebSocket.close();
        batchWebSocket = null;
    }
}

function startCurrentBatchPolling(batchId) {
    if (isOutlookBatchMode) {
        startOutlookBatchPolling(batchId);
        return;
    }

    startBatchPolling(batchId);
}

// 开始批量任务心跳
function startBatchWebSocketHeartbeat() {
    stopBatchWebSocketHeartbeat();
    batchWsHeartbeatInterval = setInterval(() => {
        if (batchWebSocket && batchWebSocket.readyState === WebSocket.OPEN) {
            batchWebSocket.send(JSON.stringify({ type: 'ping' }));
        }
    }, 25000);  // 每 25 秒发送一次心跳
}

// 停止批量任务心跳
function stopBatchWebSocketHeartbeat() {
    if (batchWsHeartbeatInterval) {
        clearInterval(batchWsHeartbeatInterval);
        batchWsHeartbeatInterval = null;
    }
}

// 发送批量任务取消请求
function cancelBatchViaWebSocket() {
    if (batchWebSocket && batchWebSocket.readyState === WebSocket.OPEN) {
        batchWebSocket.send(JSON.stringify({ type: 'cancel' }));
    }
}

// 开始轮询 Outlook 批量状态（降级方案）
function startOutlookBatchPolling(batchId) {
    batchPollingInterval = setInterval(async () => {
        try {
            const data = await api.get(`/registration/outlook-batch/${batchId}`);

            // 更新进度
            updateBatchProgress({
                total: data.total,
                completed: data.completed,
                success: data.success,
                failed: data.failed
            });

            // 输出日志
            if (data.logs && data.logs.length > 0) {
                const lastLogIndex = batchPollingInterval.lastLogIndex || 0;
                for (let i = lastLogIndex; i < data.logs.length; i++) {
                    const log = data.logs[i];
                    const logType = getLogType(log);
                    addLog(logType, log);
                }
                batchPollingInterval.lastLogIndex = data.logs.length;
            }

            // 检查是否完成
            if (data.finished) {
                stopBatchPolling();
                resetButtons();

                // 只显示一次 toast
                if (!toastShown) {
                    toastShown = true;
                    addLog('info', `[完成] Outlook 批量任务完成！成功: ${data.success}, 失败: ${data.failed}, 跳过: ${data.skipped || 0}`);
                    if (data.success > 0) {
                        toast.success(`Outlook 批量注册完成，成功 ${data.success} 个`);
                        loadRecentAccounts();
                    } else {
                        toast.warning('Outlook 批量注册完成，但没有成功注册任何账号');
                    }
                }
            }
        } catch (error) {
            console.error('轮询 Outlook 批量状态失败:', error);
        }
    }, 2000);

    batchPollingInterval.lastLogIndex = 0;
}

// ============== 页面可见性重连机制 ==============

function initVisibilityReconnect() {
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') return;

        // 页面重新可见时，检查是否需要重连（针对同页面标签切换场景）
        const wsDisconnected = !webSocket || webSocket.readyState === WebSocket.CLOSED;
        const batchWsDisconnected = !batchWebSocket || batchWebSocket.readyState === WebSocket.CLOSED;

        // 单任务重连
        if (activeTaskUuid && !taskCompleted && wsDisconnected) {
            console.log('[重连] 页面重新可见，重连单任务 WebSocket:', activeTaskUuid);
            addLog('info', '[系统] 页面重新激活，正在重连任务监控...');
            connectWebSocket(activeTaskUuid);
        }

        // 批量任务重连
        if (activeBatchId && !batchCompleted && batchWsDisconnected) {
            console.log('[重连] 页面重新可见，重连批量任务 WebSocket:', activeBatchId);
            addLog('info', '[系统] 页面重新激活，正在重连批量任务监控...');
            connectBatchWebSocket(activeBatchId);
        }
    });
}

// 页面加载时恢复进行中的任务（处理跨页面导航后回到注册页的情况）
async function restoreActiveTask() {
    const saved = sessionStorage.getItem('activeTask');
    if (!saved) return;

    let state;
    try {
        state = JSON.parse(saved);
    } catch {
        sessionStorage.removeItem('activeTask');
        return;
    }

    const { mode, task_uuid, batch_id, total } = state;

    if (mode === 'single' && task_uuid) {
        // 查询任务是否仍在运行
        try {
            const data = await api.get(`/registration/tasks/${task_uuid}`);
            if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                sessionStorage.removeItem('activeTask');
                return;
            }
            // 任务仍在运行，恢复状态
            currentTask = data;
            activeTaskUuid = task_uuid;
            taskCompleted = false;
            taskFinalStatus = null;
            toastShown = false;
            displayedLogs.clear();
            elements.startBtn.disabled = true;
            elements.cancelBtn.disabled = false;
            showTaskStatus(data);
            updateTaskStatus(data.status);
            addLog('info', `[系统] 检测到进行中的任务，正在重连监控... (${task_uuid.substring(0, 8)})`);
            connectWebSocket(task_uuid);
        } catch {
            sessionStorage.removeItem('activeTask');
        }
    } else if ((mode === 'batch' || mode === 'outlook_batch') && batch_id) {
        // 查询批量任务是否仍在运行
        const endpoint = mode === 'outlook_batch'
            ? `/registration/outlook-batch/${batch_id}`
            : `/registration/batch/${batch_id}`;
        try {
            const data = await api.get(endpoint);
            if (data.finished) {
                sessionStorage.removeItem('activeTask');
                return;
            }
            // 批量任务仍在运行，恢复状态
            currentBatch = { batch_id, ...data };
            activeBatchId = batch_id;
            isOutlookBatchMode = (mode === 'outlook_batch');
            batchCompleted = false;
            batchFinalStatus = null;
            toastShown = false;
            displayedLogs.clear();
            elements.startBtn.disabled = true;
            elements.cancelBtn.disabled = false;
            showBatchStatus({ count: total || data.total });
            updateBatchProgress(data);
            addLog('info', `[系统] 检测到进行中的批量任务，正在重连监控... (${batch_id.substring(0, 8)})`);
            connectBatchWebSocket(batch_id);
        } catch {
            sessionStorage.removeItem('activeTask');
        }
    }
}
