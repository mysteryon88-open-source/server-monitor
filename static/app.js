(() => {
  "use strict";

  const METRICS = { cpu: "cpu", memory: "memory", swap: "swap", disk: "disk" };
  const COPY = {
    appTitle: ["Монитор сервера", "Server monitor"], servers: ["Серверы", "Servers"],
    allCollect: ["Сбор работает для всех серверов", "All servers keep collecting"],
    language: ["Язык интерфейса", "Interface language"], switchLanguage: ["Переключить на английский", "Switch to Russian"], hideSidebar: ["Скрыть список серверов", "Hide server list"], showSidebar: ["Показать список серверов", "Show server list"],
    demo: ["Демо", "Demo"], demoNotice: ["Демонстрационный режим. Данные сгенерированы локально.", "Demo mode. Data is generated locally."],
    pauseNotice: ["Просмотр на паузе. Сбор данных продолжается.", "View paused. Data collection continues."], resources: ["Ресурсы сервера", "Server resources"],
    cpuLabel: ["ЦП", "CPU"], memoryLabel: ["Память", "Memory"], swapLabel: ["Подкачка", "Swap"], diskLabel: ["Диск", "Disk"],
    cpuTitle: ["Центральный процессор", "CPU utilization"], memoryTitle: ["Оперативная память", "Memory usage"], swapTitle: ["Память подкачки", "Swap usage"], diskTitle: ["Заполнение диска", "Disk usage"],
    average: ["Среднее", "Average"], peak: ["Пик", "Peak"], free: ["Свободно", "Free"], now: ["Сейчас", "Now"], paused: ["На паузе", "Paused"],
    waitingFirst: ["Ожидание первого измерения", "Waiting for the first sample"], waitingData: ["Ожидание данных", "Waiting for data"], noData: ["Нет данных", "No data"], noSamples: ["Нет измерений", "No samples"],
    noCpu: ["Нет данных о процессоре", "CPU data unavailable"], logicalCores: ["{count} лог. ЦП", "{count} logical CPUs"], ghz: ["ГГц", "GHz"], waitingCpu: ["Ожидаем измерение загрузки", "Waiting for CPU measurement"], cpuUsage: ["Загрузка процессора", "CPU utilization"],
    disabled: ["Отключена", "Disabled"], diskUnavailable: ["Диск недоступен", "Disk unavailable"], noCapacity: ["Нет данных об объёме", "Capacity unavailable"],
    binaryUnits: ["Двоичные единицы: 1 ГиБ = 1024³ байт.", "Binary units: 1 GiB = 1024³ bytes."], swapUnused: ["Подкачка не используется", "Swap is disabled"], noFilesystem: ["Нет данных о файловой системе", "Filesystem data unavailable"], noDataYet: ["Пока нет данных", "No data yet"], openHistory: ["Открыть историю.", "Open history."],
    historyWindow: ["Период истории", "History window"], history: ["История нагрузки", "Utilization history"], diskHistory: ["Данные диска · обновление около {seconds} с", "Disk history · updated about every {seconds} s"], minutes: ["{count} мин", "{count} min"], oneHour: ["1 час", "1 hour"],
    chartLabel: ["График: {title}", "Chart: {title}"], firstSample: ["Ожидаем первое измерение", "Waiting for the first sample"], historyAfterConnect: ["История появится после подключения к серверу.", "History appears after connecting to the server."],
    noPeriodData: ["В этом периоде нет данных", "No data in this period"], measurementsAfterReconnect: ["Новые измерения появятся после восстановления связи.", "New samples appear when the connection recovers."],
    swapDisabled: ["Подкачка отключена", "Swap is disabled"], swapDisabledDetail: ["На сервере не выделена память подкачки.", "The server has no swap space."], filesystemFailure: ["Не удалось прочитать сведения о файловой системе.", "Could not read filesystem information."],
    measuringCpu: ["Измеряем загрузку процессора", "Measuring CPU utilization"], twoSamples: ["Для расчёта нужны два последовательных измерения.", "Two consecutive samples are needed."], sampleCount: ["Измерений: {count}", "Samples: {count}"],
    historyDescription: ["{title}. За {minutes} мин: среднее {mean}, пик {peak}. Измерений: {count}.", "{title}. Over {minutes} min: average {mean}, peak {peak}. Samples: {count}."], noMeasurement: ["Нет измерения", "No sample"],
    resourceHistory: ["История нагрузки", "Resource history"], periodMean: ["Среднее за период", "Period average"], chartHelp: ["Для просмотра измерений используйте стрелки влево и вправо. Home — первое измерение, End — последнее. Escape — закрыть подсказку.", "Use the left and right arrows to explore samples. Home selects the first sample, End the last. Escape closes the tooltip."],
    processes: ["Топ-5 процессов", "Top 5 processes"], process: ["Процесс", "Process"], lifetimeAverage: ["ЦП: среднее с запуска", "CPU: lifetime average"], lifetimeTitle: ["ЦП — средняя загрузка процесса с запуска, может превышать 100% на нескольких ядрах.", "CPU is the process average since launch; it can exceed 100% across multiple cores."],
    processesUnavailable: ["Список процессов недоступен", "Process list unavailable"], processesEmpty: ["Нет доступных процессов", "No available processes"],
    sortCpu: ["Показать пять процессов с наибольшей загрузкой ЦП", "Show the five highest CPU consumers"], sortMemory: ["Показать пять процессов с наибольшим потреблением памяти", "Show the five highest memory consumers"],
    aboutServer: ["О сервере", "Server details"], hostname: ["Имя хоста", "Hostname"], system: ["Система", "System"], kernel: ["Ядро", "Kernel"], architecture: ["Архитектура", "Architecture"], logicalCpu: ["Логических ЦП", "Logical CPUs"], uptime: ["Работает", "Uptime"], load: ["Нагрузка 1 / 5 / 15 мин", "Load 1 / 5 / 15 min"], iowaitSteal: ["I/O wait / steal", "I/O wait / steal"], filesystem: ["Файловая система", "Filesystem"],
    cpuTemperature: ["Температура ЦП", "CPU temperature"],
    traffic: ["Трафик за 7 дней", "Traffic over 7 days"], interface: ["Сетевой интерфейс", "Network interface"], received: ["Получено", "Received"], sent: ["Отправлено", "Sent"], trafficUpdated: ["Обновлено {time}", "Updated {time}"], missingTraffic: ["Нет измерения", "No measurement"],
    trafficHint: ["Нажмите на день, чтобы увидеть объём трафика", "Select a day to see traffic amounts"], total: ["Всего", "Total"],
    hourHistory: ["История за последний час", "Last hour of history"], localTime: ["Время на этом компьютере", "This computer's time"], localTimeTitle: ["Время измерений отображается в часовом поясе этого браузера", "Sample times use this browser's time zone"],
    statusConnecting: ["Подключение", "Connecting"], statusConnected: ["Подключено", "Connected"], statusReconnecting: ["Переподключение", "Reconnecting"], statusStale: ["Данные устарели", "Stale data"], statusError: ["Нет связи", "No connection"], statusStopped: ["Остановлено", "Stopped"], statusIdle: ["Ожидание", "Waiting"], deniedLabel: ["Нет доступа", "Access denied"],
    connectingMessage: ["Подключаемся по SSH. Если нужен пароль, введите его в окне запуска.", "Connecting through SSH. Enter a password in the launch window if requested."], connectedMessage: ["Подключено по SSH.", "Connected through SSH."], reconnectingMessage: ["Восстанавливаем подключение по SSH…", "Restoring the SSH connection…"], errorMessage: ["Не удалось получить данные сервера. Проверьте окно запуска.", "Could not get server data. Check the launch window."], stoppedMessage: ["Монитор остановлен. Запустите start.cmd, чтобы продолжить сбор.", "Monitor stopped. Run start.cmd to resume collection."], idleMessage: ["Ожидаем подключение к серверу.", "Waiting to connect to the server."],
    requestReconnect: ["Запрашиваем новое подключение по SSH…", "Requesting a new SSH connection…"], staleMessage: ["Нет новых измерений с {time}. Ожидаем восстановление связи; на экране последние полученные данные.", "No new samples since {time}. Waiting for the connection to recover; showing the last received data."], connectedWaiting: ["Соединение установлено. Ожидаем первые измерения…", "Connection established. Waiting for the first samples…"],
    localConnecting: ["Запускаем локальный сбор метрик.", "Starting local metric collection."], localReconnect: ["Перезапускаем локальный сбор метрик…", "Restarting local metric collection…"],
    noConnection: ["Нет подключения", "No connection"], connectingTitle: ["Подключение…", "Connecting…"], everySecond: ["Каждую секунду", "Every second"], cadence: ["Каждые {seconds} с", "Every {seconds} s"], pause: ["Пауза", "Pause"], resume: ["Продолжить", "Resume"], fixedAt: ["Зафиксировано в {time}", "Frozen at {time}"], reload: ["Обновить страницу", "Reload page"], reconnecting: ["Подключаем…", "Connecting…"], reconnect: ["Переподключить", "Reconnect"], viewAt: ["Просмотр зафиксирован в {time}", "View frozen at {time}"], lastSample: ["Последнее измерение в {time}", "Last sample at {time}"],
    invalidResponse: ["Монитор вернул непонятный ответ. Попробуйте переподключиться.", "The monitor returned an invalid response. Try reconnecting."], denied: ["Доступ к монитору отклонён. Нажмите «Обновить страницу», чтобы получить новый ключ сеанса. Если это не поможет, откройте адрес из окна запуска.", "Access denied. Click Reload page for a new session token. If that does not help, open the address shown in the launch window."], httpError: ["Локальный монитор вернул ошибку HTTP {status}. Повторим запрос автоматически.", "The local monitor returned HTTP {status}. The request will retry automatically."],
    timeoutError: ["Локальный монитор не отвечает. Проверьте, что окно запуска открыто. Повторим запрос автоматически.", "The local monitor is not responding. Check that the launch window is open. The request will retry automatically."], reconnectError: ["Не удалось запросить переподключение. Проверьте окно запуска; повторим проверку связи автоматически.", "Could not request a reconnect. Check the launch window; the connection check will retry automatically."], networkError: ["Нет связи с локальным монитором. Проверьте, что окно запуска открыто. Повторим запрос автоматически.", "Cannot reach the local monitor. Check that the launch window is open. The request will retry automatically."], reconnectRejected: ["Не удалось запросить переподключение. Попробуйте ещё раз.", "Could not request a reconnect. Try again."], outsideApp: ["Страница открыта вне приложения или сеанс завершён. Запустите start.cmd и откройте адрес из окна запуска.", "This page is outside the app or its session has ended. Run start.cmd and open the address shown in the launch window."],
    description: ["Мониторинг SSH-серверов, WSL и этого компьютера: процессор, память, подкачка и диск.", "Monitor SSH servers, WSL and this computer: CPU, memory, swap and disk."],
  };
  const BACKEND_MESSAGES = new Map([
    ["Starting local metric collection.", "Запускаем локальный сбор метрик."],
    ["Local metric collection is running.", "Локальный сбор метрик работает."],
    ["Collecting metrics from this computer.", "Собираем данные локального компьютера."],
    ["Collecting metrics from running WSL.", "Собираем данные работающего WSL."],
    ["Restarting local metric collection.", "Перезапускаем локальный сбор данных."],
    ["The selected WSL distribution is not running. Start it and click Reconnect.", "Выбранный WSL-дистрибутив не запущен. Запустите его и нажмите «Переподключить»."],
    ["WSL is available only when the monitor runs on Windows.", "WSL доступен только при запуске монитора в Windows."],
    ["wsl.exe was not found. Check the WSL installation in Windows.", "Не найден wsl.exe. Проверьте установку WSL в Windows."],
    ["Local monitoring supports Windows and Linux only.", "Локальный сбор поддерживается только в Windows и Linux."],
    ["Could not start the local collector.", "Не удалось запустить локальный сборщик."],
    ["The local collector returned invalid data.", "Локальный сборщик вернул некорректные данные."],
    ["Could not read local system metrics.", "Не удалось прочитать локальные системные метрики."],
    ["The local collector stopped sending data.", "Локальный сборщик перестал передавать данные."],
    ["The local collector exited.", "Локальный сборщик завершился."],
    ["Could not read Windows metrics; retrying.", "Не удалось прочитать метрики Windows; повторяем сбор."],
    ["Three local collection attempts failed. Click Reconnect to try again.", "Три попытки локального сбора не удались. Нажмите «Переподключить», чтобы повторить."],
    ["Local monitoring stopped.", "Локальный мониторинг остановлен."],
    ["Three connection attempts failed. Click Reconnect to try again.", "Три попытки подключения не удались. Нажмите «Переподключить», чтобы повторить."],
    ["Connecting. Enter the SSH password in the launch window if requested.", "Подключаемся. Если SSH запросит пароль, введите его в окне запуска."],
    ["Connected through SSH", "Подключено по SSH"],
    ["Demo data", "Демонстрационные данные"],
    ["No fresh data is arriving. The last values are preserved.", "Свежие данные не приходят. Последние значения сохранены."],
    ["Reconnecting. Check the launch window if a password is needed.", "Подключаемся заново. Проверьте окно запуска, если нужен пароль."],
    ["Monitoring stopped.", "Мониторинг остановлен."],
    ["Demo stopped.", "Демонстрация остановлена."],
    ["Connecting through SSH. Password or host key prompts appear in the launch window.", "Соединяемся по SSH. Пароль или подтверждение ключа появятся в окне запуска."],
    ["Could not start SSH. Check logs/monitor.log and the launch window.", "Не удалось запустить SSH. Проверьте logs/monitor.log и окно запуска."],
    ["SSH authentication failed. Check the user, key or ssh-agent. Enter passwords in the launch window.", "SSH не принял вход. Проверьте пользователя, ключ или ssh-agent. Пароль вводится в окне запуска."],
    ["Check the server key and known_hosts using regular ssh. Verify the old key before removing it.", "Проверьте ключ сервера и known_hosts через обычный ssh. Не удаляйте старый ключ без проверки."],
    ["Check the SSH alias and Windows OpenSSH config. Details are in logs/ssh.log.", "Проверьте SSH-алиас и конфиг Windows OpenSSH. Подробности в logs/ssh.log."],
    ["Check the SSH alias and Windows OpenSSH config. Details are in logs/ssh-*.log.", "Проверьте SSH-алиас и конфиг Windows OpenSSH. Подробности в logs/ssh-*.log."],
    ["The server refused the SSH connection. Check the address, port and sshd availability.", "Сервер отклонил SSH-соединение. Проверьте адрес, порт и доступность sshd."],
    ["The SSH server is unreachable. Check the network, VPN and connection settings.", "SSH-сервер недоступен. Проверьте сеть, VPN и настройки подключения."],
    ["The collector requires Linux with /proc, sh, awk and df. Check the launch window message.", "Сборщик ожидает Linux с /proc, sh, awk и df. Проверьте сообщение в окне запуска."],
    ["The SSH connection ended. Check the launch window and logs/ssh.log; reconnecting.", "SSH-соединение завершилось. Проверьте окно запуска и logs/ssh.log; переподключаемся."],
    ["The SSH connection ended. Check the launch window and logs/ssh-*.log; reconnecting.", "SSH-соединение завершилось. Проверьте окно запуска и logs/ssh-*.log; переподключаемся."],
    ["Data stopped arriving; restoring the SSH connection.", "Данные перестали поступать; восстанавливаем SSH-соединение."],
    ["No data. Check the password, host key confirmation and Linux access in the launch window.", "Нет данных. Проверьте пароль, подтверждение ключа и доступ к Linux в окне запуска."],
    ["SSH returned invalid data. Check Linux and the user's shell.", "SSH вернул некорректные данные. Проверьте Linux и оболочку пользователя."],
    ["Could not read system metrics. Check /proc and Linux commands.", "Не удалось прочитать системные метрики. Проверьте /proc и команды Linux."],
  ]);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const $ = (id) => document.getElementById(id);
  const metricButtons = Array.from(document.querySelectorAll("[data-metric]"));
  const timeButtons = Array.from(document.querySelectorAll("[data-minutes]"));
  const token = document.querySelector('meta[name="monitor-token"]')?.content || "";
  function stored(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function remember(key, value) { try { localStorage.setItem(key, value); } catch { /* Preferences are optional. */ } }
  const savedLanguage = stored("monitor-language");
  const initialLanguage = document.querySelector('meta[name="monitor-language"]')?.content;
  let language = ["ru", "en"].includes(savedLanguage) ? savedLanguage : initialLanguage === "en" ? "en" : "ru";
  let languageChosen = ["ru", "en"].includes(savedLanguage);
  let clockFormatter;
  let axisFormatter;
  let servers = [];
  let selectedServer = null;
  let selectionVersion = 0;
  let trafficInterface = null;
  let trafficRenderKey = null;
  let selectedTrafficDay = null;
  let processSort = "cpu_percent";
  let sidebarCollapsed = stored("monitor-sidebar") === "collapsed";
  let liveSnapshot = null;
  let viewedSnapshot = null;
  let selectedMetric = "cpu";
  let windowMinutes = 5;
  let paused = false;
  let receivedAt = 0;
  let transportError = null;
  let authenticationBlocked = false;
  let failureCount = 0;
  let reconnectBusy = false;
  let pollTimer = null;
  let activePoll = null;
  let activeController = null;
  let statusTimer = null;
  let disposed = false;
  let plotContext = null;
  let hover = null;

  function t(key, values = {}) {
    return (COPY[key]?.[language === "en" ? 1 : 0] || key).replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
  }

  function applyLanguage() {
    document.documentElement.lang = language;
    document.title = t("appTitle");
    clockFormatter = new Intl.DateTimeFormat(language === "en" ? "en-GB" : "ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
    axisFormatter = new Intl.DateTimeFormat(language === "en" ? "en-GB" : "ru-RU", { hour: "2-digit", minute: "2-digit", hour12: false });
    document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll("[data-i18n-aria]").forEach((node) => node.setAttribute("aria-label", t(node.dataset.i18nAria)));
    document.querySelectorAll("[data-i18n-title]").forEach((node) => { node.title = t(node.dataset.i18nTitle); });
    document.querySelector('meta[name="description"]').content = t("description");
    setText("language-toggle", language.toUpperCase());
    $("language-toggle").setAttribute("aria-label", t("switchLanguage"));
    $("language-toggle").title = t("switchLanguage");
    document.querySelectorAll("[data-process-sort]").forEach((button) => {
      button.title = t(button.dataset.processSort === "cpu_percent" ? "sortCpu" : "sortMemory");
      button.setAttribute("aria-label", button.title);
    });
    for (const button of metricButtons) {
      button.querySelector(".metric-heading > span").textContent = t(button.dataset.metric + "Label");
      const labels = button.querySelectorAll(".metric-stats > span");
      labels.forEach((node, index) => { node.firstChild.textContent = t(button.dataset.metric === "disk" && index === 0 ? "free" : index === 1 && button.dataset.metric !== "disk" ? "peak" : "average") + " "; });
    }
    document.querySelectorAll(".history-summary > div > span:not(.legend-dot):not(#history-current-label)").forEach((node, index) => { node.textContent = t(index === 0 ? "average" : "peak"); });
    timeButtons.forEach((button) => { button.textContent = Number(button.dataset.minutes) === 60 ? t("oneHour") : t("minutes", { count: button.dataset.minutes }); });
    $("process-cpu-heading").title = t("lifetimeTitle");
    $("process-cpu-note").title = t("lifetimeTitle");
    renderSidebar();
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isNumber(value) {
    return typeof value === "number" && Number.isFinite(value);
  }

  function setText(id, value) {
    const node = $(id);
    const next = String(value);
    if (node && node.textContent !== next) node.textContent = next;
  }

  function safeText(value, fallback = "—") {
    return (typeof value === "string" && value.length > 0) || isNumber(value)
      ? String(value) : fallback;
  }

  function decimal(value, places = 1, trim = false) {
    if (!isNumber(value)) return "—";
    return value.toLocaleString(language === "en" ? "en-GB" : "ru-RU", {
      minimumFractionDigits: trim ? 0 : places, maximumFractionDigits: places, useGrouping: false,
    });
  }

  function percent(value, trim = true) {
    return isNumber(value) ? decimal(value, 1, trim) + "%" : "—";
  }

  function bytes(value) {
    if (!isNumber(value)) return "—";
    const absolute = Math.abs(value);
    const units = language === "en" ? ["B", "KiB", "MiB", "GiB", "TiB", "PiB"] : ["Б", "КиБ", "МиБ", "ГиБ", "ТиБ", "ПиБ"];
    const unit = absolute < 1 ? 0 : Math.min(units.length - 1, Math.floor(Math.log(absolute) / Math.log(1024)));
    const amount = absolute / Math.pow(1024, unit);
    return (value < 0 ? "−" : "") + decimal(amount, unit === 0 ? 0 : 2) + " " + units[unit];
  }

  function clock(timestamp) {
    return isNumber(timestamp) ? clockFormatter.format(new Date(timestamp)) : "—";
  }

  function uptime(seconds) {
    if (!isNumber(seconds) || seconds < 0) return "—";
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor(seconds / 3600) % 24;
    const minutes = Math.floor(seconds / 60) % 60;
    const units = language === "en" ? ["d", "h", "min", "s"] : ["д", "ч", "мин", "с"];
    if (days) return days + " " + units[0] + " " + hours + " " + units[1] + " " + minutes + " " + units[2];
    if (hours) return hours + " " + units[1] + " " + minutes + " " + units[2];
    if (minutes) return minutes + " " + units[2];
    return Math.floor(seconds) + " " + units[3];
  }

  function metricValue(sample, key) {
    const metric = isObject(sample) ? sample[key] : null;
    if (!isObject(metric) || (key === "swap" && metric.enabled === false)) return null;
    // df can legitimately report more than 100% when available blocks are negative.
    return isNumber(metric.percent) && metric.percent >= 0 ? metric.percent : null;
  }

  function normalizeSnapshot(raw) {
    if (!isObject(raw) || !Array.isArray(raw.history)) {
      throw new ApiError("invalidResponse");
    }
    const latest = isObject(raw.latest) ? raw.latest : null;
    const byTime = new Map();
    for (const sample of raw.history) {
      if (isObject(sample) && isNumber(sample.ts)) byTime.set(sample.ts, sample);
    }
    if (latest && isNumber(latest.ts)) byTime.set(latest.ts, latest);
    const history = Array.from(byTime.values()).sort((a, b) => a.ts - b.ts);
    return {
      status: safeText(raw.status, "connecting"),
      message: typeof raw.message === "string" ? raw.message : "",
      alias: safeText(raw.alias, "—"),
      source: ["self", "wsl"].includes(raw.source) ? raw.source : "ssh",
      name: safeText(raw.name, safeText(raw.alias)),
      server_id: typeof raw.server_id === "string" ? raw.server_id : null,
      interval: isNumber(raw.interval) && raw.interval > 0 && raw.interval <= 60 ? raw.interval : 2,
      demo: raw.demo === true,
      server_time: isNumber(raw.server_time) ? raw.server_time : Date.now(),
      last_update: isNumber(raw.last_update) ? raw.last_update : (latest?.ts ?? null),
      latest,
      history,
    };
  }

  function makeContext(snapshot) {
    const end = snapshot ? Math.max(snapshot.server_time, snapshot.latest?.ts || 0) : Date.now();
    const start = end - windowMinutes * 60000;
    const samples = snapshot ? snapshot.history.filter((sample) => sample.ts >= start && sample.ts <= end) : [];
    const gap = Math.max((snapshot?.interval || 2) * 3500, 8000);
    const stats = {};
    for (const key of Object.keys(METRICS)) {
      const values = samples.map((sample) => metricValue(sample, key)).filter(isNumber);
      const peak = values.length ? Math.max(...values) : null;
      const latest = metricValue(snapshot?.latest, key);
      const maximum = Math.max(100, peak || 0, latest || 0);
      stats[key] = {
        count: values.length,
        mean: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
        peak,
        scale: Math.ceil(maximum / 25) * 25,
      };
    }
    return { start, end, samples, gap, stats };
  }

  function svgNode(tag, attributes = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
    return node;
  }

  function chartSegments(context, key) {
    const segments = [];
    let current = [];
    let previousTime = null;
    for (const sample of context.samples) {
      const value = metricValue(sample, key);
      if (value === null || (previousTime !== null && sample.ts - previousTime > context.gap)) {
        if (current.length) segments.push(current);
        current = [];
      }
      if (value !== null) current.push({ ts: sample.ts, value });
      previousTime = sample.ts;
    }
    if (current.length) segments.push(current);
    return segments;
  }

  function drawChart(svg, context, key, large = false) {
    const height = large ? 260 : 180;
    const padding = large ? 0 : 9;
    const plotHeight = large ? height : height - 20;
    const scale = context.stats[key].scale;
    const x = (timestamp) => ((timestamp - context.start) / (context.end - context.start)) * 1000;
    const y = (value) => padding + (1 - value / scale) * plotHeight;
    const number = (value) => value.toFixed(2);
    const fragment = document.createDocumentFragment();
    const defs = svgNode("defs");
    const gradientId = svg.id + "-fill";
    const gradient = svgNode("linearGradient", {
      id: gradientId, x1: 0, x2: 0, y1: 0, y2: height, gradientUnits: "userSpaceOnUse",
    });
    gradient.append(
      svgNode("stop", { offset: "0%", "stop-color": "#1688ff", "stop-opacity": large ? ".26" : ".4" }),
      svgNode("stop", { offset: "100%", "stop-color": "#1688ff", "stop-opacity": ".015" }),
    );
    defs.append(gradient);
    fragment.append(defs);
    if (large) {
      for (let index = 0; index <= 4; index += 1) {
        const position = height * index / 4;
        fragment.append(svgNode("line", { x1: 0, x2: 1000, y1: position, y2: position, class: "chart-gridline" }));
      }
    }
    let linePath = "";
    let areaPath = "";
    const singles = [];
    for (const segment of chartSegments(context, key)) {
      const points = segment.map((point) => [x(point.ts), y(point.value)]);
      if (points.length === 1) {
        singles.push(points[0]);
        continue;
      }
      let line = "M" + number(points[0][0]) + "," + number(points[0][1]);
      for (let index = 1; index < points.length; index += 1) {
        line += "L" + number(points[index][0]) + "," + number(points[index][1]);
      }
      linePath += line;
      areaPath += line + "L" + number(points[points.length - 1][0]) + "," + height +
        "L" + number(points[0][0]) + "," + height + "Z";
    }
    if (areaPath) fragment.append(svgNode("path", { d: areaPath, fill: "url(#" + gradientId + ")" }));
    const average = context.stats[key].mean;
    if (isNumber(average)) {
      const position = y(average);
      fragment.append(svgNode("line", { x1: 0, x2: 1000, y1: position, y2: position, class: "mean-line" }));
    }
    if (linePath) fragment.append(svgNode("path", { d: linePath, class: "chart-line" }));
    for (const [pointX, pointY] of singles) {
      fragment.append(svgNode("circle", { cx: pointX, cy: pointY, r: large ? 3 : 2.5, fill: "#1688ff" }));
    }
    svg.replaceChildren(fragment);
  }

  function metricDetail(sample, key) {
    if (!sample) return t("waitingFirst");
    const value = sample[key];
    if (key === "cpu") {
      if (!isObject(value)) return t("noCpu");
      const parts = [];
      if (isNumber(value.cores) && value.cores > 0) parts.push(t("logicalCores", { count: value.cores }));
      if (isNumber(value.mhz) && value.mhz > 0) parts.push(decimal(value.mhz / 1000, 2) + " " + t("ghz"));
      return parts.join(" · ") || t(metricValue(sample, key) === null ? "waitingCpu" : "cpuUsage");
    }
    if (key === "swap" && value?.enabled === false) return t("disabled");
    if (!isObject(value)) return t(key === "disk" ? "diskUnavailable" : "noData");
    if (isNumber(value.used) && isNumber(value.total)) return bytes(value.used) + " / " + bytes(value.total);
    return t(key === "disk" ? "diskUnavailable" : "noCapacity");
  }

  function renderCards(context) {
    const latest = viewedSnapshot?.latest;
    for (const key of Object.keys(METRICS)) {
      const value = metricValue(latest, key);
      const stats = context.stats[key];
      setText(key + "-value", isNumber(value) ? decimal(value) : "—");
      $(key + "-unit").hidden = value === null;
      const detail = metricDetail(latest, key);
      setText(key + "-detail", detail);
      $(key + "-detail").title = key === "cpu"
        ? safeText(latest?.cpu?.model, detail)
        : detail + ". " + t("binaryUnits");
      setText(key + "-average", percent(stats.mean));
      if (key === "disk") {
        setText("disk-free", bytes(latest?.disk?.available));
      } else {
        setText(key + "-peak", percent(stats.peak));
      }
      drawChart($(key + "-sparkline"), context, key);
      $(key + "-empty").hidden = stats.count > 0;
      setText(key + "-empty", t(key === "swap" && latest?.swap?.enabled === false
        ? "swapUnused" : key === "disk" && latest && value === null ? "noFilesystem" : "noDataYet"));
      const button = metricButtons.find((item) => item.dataset.metric === key);
      button.classList.toggle("is-selected", selectedMetric === key);
      button.setAttribute("aria-pressed", String(selectedMetric === key));
      button.setAttribute("aria-label", t(key + "Label") + ": " +
        (value === null ? detail : percent(value, false) + ". " + detail) + ". " + t("openHistory"));
    }
  }

  function renderFacts() {
    const latest = viewedSnapshot?.latest;
    const host = isObject(latest?.host) ? latest.host : {};
    setText("fact-hostname", safeText(host.hostname));
    setText("fact-os", safeText(host.os));
    setText("fact-kernel", safeText(host.kernel));
    setText("fact-arch", safeText(host.arch));
    setText("fact-cores", safeText(latest?.cpu?.cores));
    setText("fact-uptime", uptime(host.uptime));
    setText("fact-load", Array.isArray(host.load) && host.load.length >= 3
      ? host.load.slice(0, 3).map((value) => decimal(value, 2)).join(" / ") : "—");
    setText("fact-cpu-wait", percent(latest?.cpu?.iowait) + " / " + percent(latest?.cpu?.steal));
    setText("fact-disk", safeText(latest?.disk?.device, latest ? t("noData") : "—"));
    setText("fact-disk-path", safeText(latest?.disk?.path));
    $("fact-disk-path").hidden = typeof latest?.disk?.path !== "string";
    $("fact-disk-path").title = safeText(latest?.disk?.path, "");
    const temperature = latest?.cpu?.temperature_c;
    const hasTemperature = isNumber(temperature) && temperature >= 0;
    $("temperature-reading").hidden = !hasTemperature;
    setText("fact-temperature", hasTemperature ? decimal(temperature, 1) + " °C" : "—");
    document.querySelectorAll(".server-facts dd").forEach((node) => { node.title = node.textContent; });
  }

  function normalizeServers(items) {
    if (!Array.isArray(items) || !items.length) throw new ApiError("invalidResponse");
    const ids = new Set();
    return items.map((item) => {
      if (!isObject(item) || typeof item.id !== "string" || !item.id || ids.has(item.id)) throw new ApiError("invalidResponse");
      ids.add(item.id);
      return { id: item.id, name: safeText(item.name, safeText(item.alias)), alias: safeText(item.alias),
        source: ["self", "wsl"].includes(item.source) ? item.source : "ssh",
        status: ["connecting", "connected", "reconnecting", "error", "stopped", "idle"].includes(item.status) ? item.status : "error", demo: item.demo === true };
    });
  }

  function renderSidebar() {
    const list = $("server-list");
    const rank = (server) => server.source === "self" ? -1 : server.status === "connected" ? 0 : server.status === "connecting" ? 1 : 2;
    const ordered = [...servers].sort((a, b) => rank(a) - rank(b));
    const current = Array.from(list.children);
    if (current.length !== ordered.length || current.some((node, index) => node.dataset.server !== ordered[index].id)) {
      const focusedServer = document.activeElement?.dataset.server;
      const buttons = ordered.map((server) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "server-item";
        button.dataset.server = server.id;
        const dot = document.createElement("span");
        dot.className = "status-dot";
        dot.setAttribute("aria-hidden", "true");
        const name = document.createElement("span");
        name.className = "server-item-name";
        const status = document.createElement("span");
        status.className = "server-item-status";
        button.append(dot, name, status);
        button.addEventListener("click", () => selectServer(server.id));
        return button;
      });
      list.replaceChildren(...buttons);
      if (focusedServer) buttons.find((button) => button.dataset.server === focusedServer)?.focus({ preventScroll: true });
    }
    Array.from(list.children).forEach((button, index) => {
      const server = ordered[index];
      const displayName = server.source === "self" ? "SELF" : server.name;
      button.dataset.state = server.status;
      button.children[1].textContent = displayName;
      const label = t("status" + server.status[0].toUpperCase() + server.status.slice(1));
      button.children[2].textContent = label + (server.demo ? " · " + t("demo") : "");
      button.title = displayName + " · " + server.alias;
      button.setAttribute("aria-label", displayName + ": " + label);
      button.setAttribute("aria-pressed", String(server.id === selectedServer));
      button.classList.toggle("is-selected", server.id === selectedServer);
    });
    document.querySelector(".app-shell").classList.toggle("sidebar-collapsed", sidebarCollapsed);
    $("server-sidebar").hidden = sidebarCollapsed;
    $("sidebar-toggle").setAttribute("aria-expanded", String(!sidebarCollapsed));
    $("sidebar-toggle").setAttribute("aria-label", t(sidebarCollapsed ? "showSidebar" : "hideSidebar"));
    $("sidebar-toggle").title = t(sidebarCollapsed ? "showSidebar" : "hideSidebar");
  }

  function selectServer(id) {
    if (id === selectedServer || !servers.some((server) => server.id === id)) return;
    selectionVersion += 1;
    selectedServer = id;
    if (activeController) activeController.abort();
    activePoll = null;
    clearTimeout(pollTimer);
    liveSnapshot = null;
    viewedSnapshot = null;
    paused = false;
    receivedAt = 0;
    transportError = null;
    failureCount = 0;
    reconnectBusy = false;
    trafficInterface = null;
    selectedTrafficDay = null;
    closeInterfaces();
    clearHover();
    renderSidebar();
    renderData();
    renderStatus();
    beginPoll();
  }

  function renderProcesses() {
    const processes = viewedSnapshot?.latest?.processes;
    const rows = Array.isArray(processes) ? processes.filter(isObject).sort((a, b) =>
      (isNumber(b[processSort]) ? b[processSort] : -1) - (isNumber(a[processSort]) ? a[processSort] : -1)
      || (a.pid || 0) - (b.pid || 0)).slice(0, 5) : [];
    $("process-cpu-heading").setAttribute("aria-sort", processSort === "cpu_percent" ? "descending" : "none");
    $("process-memory-heading").setAttribute("aria-sort", processSort === "memory_bytes" ? "descending" : "none");
    $("process-list").replaceChildren(...rows.map((process) => {
      const row = document.createElement("tr");
      for (const value of [safeText(process.name), safeText(process.pid), percent(process.cpu_percent), bytes(process.memory_bytes)]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        cell.title = value;
        row.append(cell);
      }
      row.children[2].title = t("lifetimeTitle") + " " + percent(process.cpu_percent);
      return row;
    }));
    $("process-empty").hidden = rows.length > 0;
    document.querySelector(".process-table").hidden = rows.length === 0;
    setText("process-empty", t(!viewedSnapshot?.latest ? "waitingFirst" : Array.isArray(processes) ? "processesEmpty" : "processesUnavailable"));
  }

  function calendarDate(value, full = false) {
    const match = typeof value === "string" && /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return safeText(value);
    // vnStat dates belong to the server's calendar, independently of browser time zone.
    const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
    return new Intl.DateTimeFormat(language === "en" ? "en-GB" : "ru-RU", { day: "2-digit", month: "2-digit", ...(full ? { year: "numeric" } : {}), timeZone: "UTC" }).format(date);
  }

  function trafficAmount(value) {
    if (!isNumber(value) || value < 0) return "—";
    if (value < 1024 ** 3) return bytes(value);
    return new Intl.NumberFormat(language === "en" ? "en-GB" : "ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value / (1024 ** 3)) + " GiB";
  }

  function closeInterfaces(focus = false) {
    $("interface-options").hidden = true;
    $("traffic-interface").setAttribute("aria-expanded", "false");
    if (focus) $("traffic-interface").focus();
  }

  function openInterfaces(last = false) {
    const options = Array.from($("interface-options").children);
    if (!options.length) return;
    $("interface-options").hidden = false;
    $("traffic-interface").setAttribute("aria-expanded", "true");
    (last ? options.at(-1) : options.find((option) => option.dataset.interface === trafficInterface) || options[0]).focus();
  }

  function trafficDayText(day) {
    return calendarDate(day.date, true) + " · ↓ " + t("received") + ": " + trafficAmount(day.rx)
      + " · ↑ " + t("sent") + ": " + trafficAmount(day.tx) + " · Σ " + t("total") + ": "
      + trafficAmount(isNumber(day.rx) && isNumber(day.tx) ? day.rx + day.tx : null);
  }

  function showTrafficDay(day) {
    selectedTrafficDay = day.date;
    setText("traffic-day-detail", trafficDayText(day));
    Array.from($("traffic-days").children).forEach((column) => {
      column.setAttribute("aria-pressed", String(column.dataset.date === selectedTrafficDay));
    });
  }

  function renderTraffic() {
    const traffic = viewedSnapshot?.latest?.traffic;
    const interfaces = isObject(traffic) && Array.isArray(traffic.interfaces) ? traffic.interfaces.filter((item) => isObject(item) && typeof item.name === "string" && Array.isArray(item.days)) : [];
    $("traffic-panel").hidden = interfaces.length === 0;
    if (!interfaces.length) {
      trafficRenderKey = null;
      selectedTrafficDay = null;
      closeInterfaces();
      $("traffic-days").replaceChildren();
      return;
    }
    if (!interfaces.some((item) => item.name === trafficInterface)) trafficInterface = interfaces.some((item) => item.name === traffic.default_interface) ? traffic.default_interface : interfaces[0].name;
    const renderKey = JSON.stringify([selectedServer, traffic.updated_at, trafficInterface, language]);
    // Keep focused day readings in place between vnStat refreshes.
    if (trafficRenderKey === renderKey) return;
    trafficRenderKey = renderKey;
    const options = $("interface-options");
    if (options.children.length !== interfaces.length || Array.from(options.children).some((option, index) => option.dataset.interface !== interfaces[index].name)) {
      options.replaceChildren(...interfaces.map((item) => {
        const option = document.createElement("button");
        option.type = "button";
        option.tabIndex = -1;
        option.setAttribute("role", "option");
        option.dataset.interface = item.name;
        option.textContent = item.name;
        option.addEventListener("click", () => {
          trafficInterface = item.name;
          selectedTrafficDay = null;
          closeInterfaces(true);
          renderTraffic();
        });
        return option;
      }));
    }
    Array.from(options.children).forEach((option) => option.setAttribute("aria-selected", String(option.dataset.interface === trafficInterface)));
    setText("interface-name", trafficInterface);
    $("traffic-interface").setAttribute("aria-label", t("interface") + ": " + trafficInterface);
    $("traffic-interface").disabled = interfaces.length < 2;
    const selected = interfaces.find((item) => item.name === trafficInterface);
    setText("traffic-rx", trafficAmount(selected.rx));
    setText("traffic-tx", trafficAmount(selected.tx));
    const days = selected.days.filter(isObject).slice(-7);
    const maximum = Math.max(1, ...days.flatMap((day) => [day.rx, day.tx].filter((value) => isNumber(value) && value >= 0)));
    $("traffic-days").replaceChildren(...days.map((day) => {
      const column = document.createElement("button");
      column.type = "button";
      column.className = "traffic-day";
      const description = trafficDayText(day);
      column.title = description;
      column.setAttribute("aria-label", description);
      column.dataset.date = day.date;
      column.setAttribute("aria-pressed", String(day.date === selectedTrafficDay));
      column.addEventListener("click", () => showTrafficDay(day));
      const bars = document.createElement("span");
      bars.className = "traffic-bars";
      bars.setAttribute("aria-hidden", "true");
      for (const key of ["rx", "tx"]) {
        if (!isNumber(day[key]) || day[key] < 0) continue;
        const bar = document.createElement("span");
        bar.className = "traffic-bar " + key;
        bar.style.height = Math.max(1, day[key] / maximum * 34) + "px";
        bars.append(bar);
      }
      if (!bars.children.length) {
        const missing = document.createElement("span");
        missing.className = "traffic-missing";
        missing.textContent = "—";
        bars.append(missing);
      }
      const label = document.createElement("span");
      label.className = "traffic-date";
      label.textContent = calendarDate(day.date);
      column.append(bars, label);
      return column;
    }));
    const activeDay = days.find((day) => day.date === selectedTrafficDay);
    setText("traffic-day-detail", activeDay ? trafficDayText(activeDay) : t("trafficHint"));
    setText("traffic-period", "vnStat · " + (days.length ? calendarDate(days[0].date) + "–" + calendarDate(days.at(-1).date) : "—"));
    setText("traffic-updated", t("trafficUpdated", { time: clock(traffic.updated_at) }));
  }

  function renderHistory(context) {
    const key = selectedMetric;
    const stats = context.stats[key];
    const latest = viewedSnapshot?.latest;
    setText("history-title", t(key + "Title"));
    const eyebrow = document.querySelector(".history-heading .eyebrow");
    const interval = viewedSnapshot?.interval || 2;
    const diskInterval = Math.ceil(10 / interval) * interval;
    const eyebrowText = key === "disk" ? t("diskHistory", { seconds: diskInterval }) : t("history");
    if (eyebrow.textContent !== eyebrowText) eyebrow.textContent = eyebrowText;
    setText("history-current-label", t(paused ? "paused" : "now"));
    setText("history-current", percent(metricValue(latest, key), false));
    setText("history-average", percent(stats.mean));
    setText("history-peak", percent(stats.peak));
    $("plot-frame").setAttribute("aria-label", t("chartLabel", { title: t(key + "Title") }));
    drawChart($("history-svg"), context, key, true);
    document.querySelectorAll(".y-axis span").forEach((node, index) => {
      node.textContent = decimal(stats.scale * (4 - index) / 4, 1, true) + "%";
    });
    Array.from($("x-axis").children).forEach((node, index) => {
      node.textContent = axisFormatter.format(new Date(context.start + (context.end - context.start) * index / 4));
    });
    $("history-empty").hidden = stats.count > 0;
    let emptyTitle = t("firstSample");
    let emptyDetail = t("historyAfterConnect");
    if (latest) {
      emptyTitle = t("noPeriodData");
      emptyDetail = t("measurementsAfterReconnect");
    }
    if (key === "swap" && latest?.swap?.enabled === false) {
      emptyTitle = t("swapDisabled");
      emptyDetail = t("swapDisabledDetail");
    } else if (key === "disk" && latest && metricValue(latest, key) === null) {
      emptyTitle = t("diskUnavailable");
      emptyDetail = t("filesystemFailure");
    } else if (key === "cpu" && latest && latest.cpu && metricValue(latest, key) === null && context.samples.length < 2) {
      emptyTitle = t("measuringCpu");
      emptyDetail = t("twoSamples");
    }
    setText("history-empty-title", emptyTitle);
    setText("history-empty-detail", emptyDetail);
    setText("sample-count", stats.count ? t("sampleCount", { count: stats.count }) : t("noSamples"));
    setText("history-description", stats.count
      ? t("historyDescription", { title: t(key + "Title"), minutes: windowMinutes, mean: percent(stats.mean), peak: percent(stats.peak), count: stats.count })
      : emptyTitle + ". " + emptyDetail);
    for (const button of timeButtons) {
      const active = Number(button.dataset.minutes) === windowMinutes;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
    plotContext = context;
    if (hover) updateHover();
  }

  function renderData() {
    const context = makeContext(viewedSnapshot);
    renderCards(context);
    renderFacts();
    renderHistory(context);
    renderProcesses();
    renderTraffic();
  }

  function nearestIndex(samples, timestamp) {
    let left = 0;
    let right = samples.length - 1;
    while (left < right) {
      const middle = Math.floor((left + right) / 2);
      if (samples[middle].ts < timestamp) left = middle + 1;
      else right = middle;
    }
    if (left > 0 && Math.abs(samples[left - 1].ts - timestamp) <= Math.abs(samples[left].ts - timestamp)) {
      return left - 1;
    }
    return left;
  }

  function hideTooltip() {
    $("chart-tooltip").hidden = true;
    $("chart-crosshair").hidden = true;
    $("chart-dot").hidden = true;
  }

  function clearHover() {
    hover = null;
    hideTooltip();
  }

  function updateHover(announce = false) {
    if (!hover || !plotContext?.samples.length) {
      hideTooltip();
      return;
    }
    const context = plotContext;
    const target = hover.mode === "keyboard"
      ? hover.ts : context.start + hover.ratio * (context.end - context.start);
    const index = nearestIndex(context.samples, target);
    const nearest = context.samples[index];
    const hasSample = hover.mode === "keyboard" || Math.abs(nearest.ts - target) <= context.gap / 2;
    const sample = hasSample ? nearest : null;
    const timestamp = sample ? sample.ts : target;
    const value = metricValue(sample, selectedMetric);
    const ratio = Math.max(0, Math.min(1, (timestamp - context.start) / (context.end - context.start)));
    const frame = $("plot-frame");
    const pixelX = ratio * frame.clientWidth;
    const valueLabel = value === null
      ? t(selectedMetric === "swap" && sample?.swap?.enabled === false ? "disabled" : "noMeasurement")
      : percent(value, false);
    setText("tooltip-time", clock(timestamp));
    setText("tooltip-value", valueLabel);
    $("chart-crosshair").style.left = (ratio * 100) + "%";
    $("chart-crosshair").hidden = false;
    $("chart-dot").hidden = value === null;
    if (value !== null) {
      $("chart-dot").style.left = (ratio * 100) + "%";
      $("chart-dot").style.top = ((1 - value / context.stats[selectedMetric].scale) * 100) + "%";
    }
    const tooltip = $("chart-tooltip");
    tooltip.hidden = false;
    const width = tooltip.offsetWidth || 140;
    const position = pixelX + width + 18 < frame.clientWidth ? pixelX + 12 : pixelX - width - 12;
    tooltip.style.left = Math.max(6, Math.min(frame.clientWidth - width - 6, position)) + "px";
    if (announce) setText("keyboard-reading", clock(timestamp) + ", " + t(selectedMetric + "Label") + ": " + valueLabel);
  }

  function handlePointer(event) {
    if (!plotContext?.samples.length) return;
    const bounds = $("plot-frame").getBoundingClientRect();
    hover = { mode: "pointer", ratio: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)) };
    updateHover();
  }

  function renderStatus() {
    const snapshot = liveSnapshot;
    const chosen = servers.find((server) => server.id === selectedServer);
    const interval = snapshot?.interval || 2;
    const source = snapshot?.source || chosen?.source || "ssh";
    let status = snapshot?.status || chosen?.status || "connecting";
    const messageKeys = { connecting: "connectingMessage", connected: "connectedMessage", reconnecting: "reconnectingMessage", error: "errorMessage", stopped: "stoppedMessage", idle: "idleMessage" };
    let message = snapshot?.message ? (language === "ru" ? BACKEND_MESSAGES.get(snapshot.message) || snapshot.message : snapshot.message) : t(messageKeys[status] || "errorMessage");
    if (!snapshot?.message && source !== "ssh" && ["connecting", "reconnecting", "idle"].includes(status)) message = t("localConnecting");
    if (authenticationBlocked) {
      status = "error";
      message = t(transportError?.key || "outsideApp", transportError?.values);
    } else if (reconnectBusy) {
      status = "reconnecting";
      message = t(source === "ssh" ? "requestReconnect" : "localReconnect");
    } else if (transportError) {
      status = "error";
      message = t(transportError.key, transportError.values);
    } else if (status === "connected" && snapshot) {
      const last = snapshot.last_update;
      const age = isNumber(last)
        ? Math.max(0, snapshot.server_time - last) + Math.max(0, Date.now() - receivedAt) : null;
      if (age !== null && age > Math.max(10000, interval * 4000)) {
        status = "stale";
        message = t("staleMessage", { time: clock(last) });
      } else if (!snapshot.latest) {
        status = "connecting";
        message = t("connectedWaiting");
      }
    }
    const statusLabels = {
      connecting: t("statusConnecting"), connected: t("statusConnected"), reconnecting: t("statusReconnecting"),
      stale: t("statusStale"), error: t(authenticationBlocked ? "deniedLabel" : "statusError"), stopped: t("statusStopped"), idle: t("statusIdle"),
    };
    if (!Object.hasOwn(statusLabels, status)) status = "error";
    $("connection-status").dataset.state = status;
    setText("connection-label", statusLabels[status]);
    $("status-notice").hidden = status === "connected";
    $("status-notice").dataset.tone = status === "error" ? "error"
      : status === "stale" || status === "reconnecting" || status === "stopped" ? "warning" : "info";
    setText("status-message", message);
    const alias = source === "self" ? "SELF" : snapshot?.name || chosen?.name || t(authenticationBlocked ? "noConnection" : "connectingTitle");
    setText("server-alias", alias);
    $("server-alias").title = alias;
    document.title = selectedServer !== null ? alias + " · " + t("appTitle") : t("appTitle");
    const isDemo = (snapshot?.demo ?? chosen?.demo) === true;
    $("demo-badge").hidden = !isDemo;
    $("demo-notice").hidden = !isDemo;
    const protocol = document.querySelector(".protocol-badge");
    const protocolText = isDemo ? t("demo").toUpperCase() : source.toUpperCase();
    if (protocol.textContent !== protocolText) protocol.textContent = protocolText;
    setText("refresh-cadence", interval === 1 ? t("everySecond") : t("cadence", { seconds: interval }));
    $("pause-button").disabled = !viewedSnapshot?.latest;
    $("pause-button").setAttribute("aria-pressed", String(paused));
    setText("pause-label", t(paused ? "resume" : "pause"));
    $("pause-icon").setAttribute("href", paused ? "#icon-play" : "#icon-pause");
    $("pause-notice").hidden = !paused;
    setText("pause-time", t("fixedAt", { time: clock(viewedSnapshot?.latest?.ts) }));
    $("reconnect-button").disabled = reconnectBusy || (selectedServer === null && !authenticationBlocked);
    setText("reconnect-label", t(authenticationBlocked ? "reload" : reconnectBusy ? "reconnecting" : "reconnect"));
    const lastShown = viewedSnapshot?.latest?.ts ?? viewedSnapshot?.last_update;
    setText("last-update", isNumber(lastShown)
      ? t(paused ? "viewAt" : "lastSample", { time: clock(lastShown) }) : t("waitingData"));
  }

  class ApiError extends Error {
    constructor(key, authentication = false, values = {}) {
      super(t(key, values));
      this.key = key;
      this.values = values;
      this.authentication = authentication;
    }
  }

  async function requestJSON(path, method, controller) {
    const response = await fetch(path, {
      method,
      headers: { "X-Monitor-Token": token, Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    });
    if (response.status === 401 || response.status === 403) {
      throw new ApiError("denied", true);
    }
    if (!response.ok) throw new ApiError("httpError", false, { status: response.status });
    try {
      return await response.json();
    } catch {
      throw new ApiError("invalidResponse");
    }
  }

  function handleRequestError(error, reconnect = false) {
    if (error instanceof ApiError) {
      transportError = { key: error.key, values: error.values };
      authenticationBlocked = error.authentication;
    } else if (error?.name === "AbortError") {
      transportError = { key: "timeoutError" };
    } else {
      transportError = { key: reconnect ? "reconnectError" : "networkError" };
    }
    failureCount += 1;
  }

  async function performPoll() {
    const version = selectionVersion;
    const controller = new AbortController();
    activeController = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      if (!servers.length) {
        const catalog = await requestJSON("/api/servers", "GET", controller);
        if (disposed || version !== selectionVersion) return;
        servers = normalizeServers(catalog?.servers);
        selectedServer = servers.some((server) => server.id === catalog.default_server) ? catalog.default_server : servers[0].id;
        if (!languageChosen && ["ru", "en"].includes(catalog.language)) {
          language = catalog.language;
          applyLanguage();
        }
        renderSidebar();
        renderStatus();
      }
      const id = selectedServer;
      const raw = await requestJSON("/api/snapshot?server=" + encodeURIComponent(id), "GET", controller);
      if (disposed || version !== selectionVersion || id !== selectedServer) return;
      if (raw?.server_id !== id) throw new ApiError("invalidResponse");
      liveSnapshot = normalizeSnapshot(raw);
      if (Array.isArray(raw.servers)) {
        servers = normalizeServers(raw.servers);
        renderSidebar();
      }
      receivedAt = Date.now();
      failureCount = 0;
      transportError = null;
      if (!paused) {
        viewedSnapshot = liveSnapshot;
        renderData();
      }
      renderStatus();
    } catch (error) {
      if (disposed || version !== selectionVersion || (reconnectBusy && error?.name === "AbortError")) return;
      handleRequestError(error);
      renderStatus();
    } finally {
      clearTimeout(timeout);
      if (activeController === controller) activeController = null;
    }
  }

  function beginPoll() {
    if (disposed || authenticationBlocked || reconnectBusy || activePoll) return;
    clearTimeout(pollTimer);
    const version = selectionVersion;
    const task = performPoll();
    activePoll = task;
    const finish = () => {
      if (activePoll !== task) return;
      activePoll = null;
      if (disposed || version !== selectionVersion || authenticationBlocked || reconnectBusy) return;
      const normalDelay = (liveSnapshot?.interval || 2) * 1000;
      const retryDelay = failureCount ? Math.min(15000, normalDelay * Math.pow(2, Math.min(failureCount, 3))) : normalDelay;
      pollTimer = setTimeout(beginPoll, retryDelay);
    };
    void task.then(finish, finish);
  }

  async function reconnect() {
    if (authenticationBlocked) {
      window.location.reload();
      return;
    }
    if (reconnectBusy || disposed || selectedServer === null) return;
    const id = selectedServer;
    const version = selectionVersion;
    reconnectBusy = true;
    clearTimeout(pollTimer);
    renderStatus();
    if (activeController) activeController.abort();
    if (activePoll) await activePoll.catch(() => {});
    if (disposed || version !== selectionVersion) return;
    const controller = new AbortController();
    activeController = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const result = await requestJSON("/api/reconnect?server=" + encodeURIComponent(id), "POST", controller);
      if (disposed || version !== selectionVersion) return;
      if (!isObject(result) || result.ok !== true) throw new ApiError("reconnectRejected");
      transportError = null;
      failureCount = 0;
    } catch (error) {
      if (!disposed && version === selectionVersion) handleRequestError(error, true);
    } finally {
      clearTimeout(timeout);
      if (activeController === controller) activeController = null;
      if (version === selectionVersion) reconnectBusy = false;
      if (!disposed && version === selectionVersion) {
        renderStatus();
        beginPoll();
      }
    }
  }

  $("language-toggle").addEventListener("click", () => {
    language = language === "ru" ? "en" : "ru";
    languageChosen = true;
    remember("monitor-language", language);
    applyLanguage();
    renderData();
    renderStatus();
  });
  $("sidebar-toggle").addEventListener("click", () => {
    sidebarCollapsed = !sidebarCollapsed;
    remember("monitor-sidebar", sidebarCollapsed ? "collapsed" : "open");
    renderSidebar();
    if (hover) updateHover();
  });
  $("traffic-interface").addEventListener("click", () => {
    if ($("interface-options").hidden) openInterfaces(); else closeInterfaces();
  });
  $("interface-picker").addEventListener("keydown", (event) => {
    if (event.key === "Escape") { closeInterfaces(true); event.preventDefault(); return; }
    if (event.key === "Tab") { closeInterfaces(); return; }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if ($("interface-options").hidden) { openInterfaces(event.key === "End"); return; }
    const options = Array.from($("interface-options").children);
    const index = options.indexOf(document.activeElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
    options[next]?.focus();
  });
  document.addEventListener("click", (event) => { if (!$("interface-picker").contains(event.target)) closeInterfaces(); });
  $("interface-picker").addEventListener("focusout", (event) => { if (!$("interface-picker").contains(event.relatedTarget)) closeInterfaces(); });
  document.querySelectorAll("[data-process-sort]").forEach((button) => button.addEventListener("click", () => {
    processSort = button.dataset.processSort;
    renderProcesses();
  }));
  for (const button of metricButtons) {
    button.addEventListener("click", () => {
      selectedMetric = button.dataset.metric;
      clearHover();
      renderData();
    });
  }
  for (const button of timeButtons) {
    button.addEventListener("click", () => {
      windowMinutes = Number(button.dataset.minutes);
      clearHover();
      renderData();
    });
  }
  $("pause-button").addEventListener("click", () => {
    if (!viewedSnapshot?.latest) return;
    paused = !paused;
    if (!paused && liveSnapshot) viewedSnapshot = liveSnapshot;
    clearHover();
    renderData();
    renderStatus();
  });
  $("reconnect-button").addEventListener("click", () => { void reconnect(); });
  $("plot-frame").addEventListener("pointermove", handlePointer);
  $("plot-frame").addEventListener("pointerdown", handlePointer);
  $("plot-frame").addEventListener("pointerleave", () => {
    if (hover?.mode === "pointer") clearHover();
  });
  $("plot-frame").addEventListener("focus", () => {
    if (!plotContext?.samples.length) return;
    hover = { mode: "keyboard", ts: plotContext.samples[plotContext.samples.length - 1].ts };
    updateHover(true);
  });
  $("plot-frame").addEventListener("blur", () => {
    if (hover?.mode === "keyboard") clearHover();
  });
  $("plot-frame").addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      clearHover();
      return;
    }
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) || !plotContext?.samples.length) return;
    event.preventDefault();
    const samples = plotContext.samples;
    let index = hover?.mode === "keyboard" ? nearestIndex(samples, hover.ts) : samples.length - 1;
    if (event.key === "ArrowLeft") index = Math.max(0, index - 1);
    if (event.key === "ArrowRight") index = Math.min(samples.length - 1, index + 1);
    if (event.key === "Home") index = 0;
    if (event.key === "End") index = samples.length - 1;
    hover = { mode: "keyboard", ts: samples[index].ts };
    updateHover(true);
  });
  window.addEventListener("resize", () => { if (hover) updateHover(); });
  window.addEventListener("pagehide", () => {
    disposed = true;
    clearTimeout(pollTimer);
    clearInterval(statusTimer);
    if (activeController) activeController.abort();
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      disposed = false;
      reconnectBusy = false;
      statusTimer = setInterval(renderStatus, 1000);
      beginPoll();
    }
  });

  applyLanguage();
  renderData();
  if (!token || token === "__MONITOR_TOKEN__") {
    authenticationBlocked = true;
    transportError = { key: "outsideApp" };
  }
  renderStatus();
  statusTimer = setInterval(renderStatus, 1000);
  beginPoll();
})();
