const { createApp, reactive, computed, onMounted, watch } = Vue;

function parseTextarea(value) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

createApp({
  setup() {
    const initialElement = document.getElementById("initial-wikis");
    const initialData = initialElement ? JSON.parse(initialElement.textContent) : [];

    const configurationStorageKey = "configurationOpen";
    const selectedWikiStorageKey = "selectedWikiId";
    const sortOrderStorageKey = "pendingSortOrder";
    const pageDisplayLimit = 100;
    const showDiffSetting = localStorage.getItem('showDiffsSetting') === 'false'

    function loadFromStorage(key) {
      if (typeof window === "undefined") {
        return null;
      }
      try {
        return window.localStorage.getItem(key);
      } catch (error) {
        return null;
      }
    }

    function saveToStorage(key, value) {
      if (typeof window === "undefined") {
        return;
      }
      try {
        if (value === null || typeof value === "undefined") {
          window.localStorage.removeItem(key);
        } else {
          window.localStorage.setItem(key, String(value));
        }
      } catch (error) {
        // Ignore storage errors.
      }
    }

    function loadConfigurationOpen() {
      return loadFromStorage(configurationStorageKey) === "true";
    }

    function persistConfigurationOpen(value) {
      saveToStorage(configurationStorageKey, value ? "true" : "false");
    }

    function loadSelectedWikiId(wikis) {
      if (!Array.isArray(wikis) || !wikis.length) {
        return "";
      }
      const storedValue = loadFromStorage(selectedWikiStorageKey);
      if (storedValue === null) {
        return wikis[0].id;
      }
      const parsedValue = Number(storedValue);
      if (!Number.isNaN(parsedValue)) {
        const matchedWiki = wikis.find((wiki) => wiki.id === parsedValue || Number(wiki.id) === parsedValue);
        if (matchedWiki) {
          return matchedWiki.id;
        }
      }
      return wikis[0].id;
    }

    function persistSelectedWikiId(value) {
      if (value === "") {
        saveToStorage(selectedWikiStorageKey, null);
        return;
      }
      saveToStorage(selectedWikiStorageKey, value);
    }

    function loadSortOrder() {
      const storedValue = loadFromStorage(sortOrderStorageKey);
      if (storedValue === "newest" || storedValue === "oldest" || storedValue === "random") {
        return storedValue;
      }
      return "newest";
    }

    function persistSortOrder(value) {
      saveToStorage(sortOrderStorageKey, value);
    }

    function getPendingTimestamp(page) {
      if (!page || !page.pending_since) {
        return 0;
      }
      const timestamp = new Date(page.pending_since).getTime();
      return Number.isNaN(timestamp) ? 0 : timestamp;
    }

    function shufflePages(pages) {
      const shuffled = [...pages];
      for (let index = shuffled.length - 1; index > 0; index -= 1) {
        const swapIndex = Math.floor(Math.random() * (index + 1));
        [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
      }
      return shuffled;
    }

    function sortPages(pages, order) {
      if (!Array.isArray(pages)) {
        return [];
      }
      if (order === "random") {
        return shufflePages(pages);
      }
      const sorted = [...pages];
      sorted.sort((first, second) => {
        const firstTimestamp = getPendingTimestamp(first);
        const secondTimestamp = getPendingTimestamp(second);
        if (order === "oldest") {
          return firstTimestamp - secondTimestamp;
        }
        return secondTimestamp - firstTimestamp;
      });
      return sorted;
    }

    const state = reactive({
      wikis: initialData,
      selectedWikiId: initialData.length ? loadSelectedWikiId(initialData) : "",
      sortOrder: loadSortOrder(),
      pages: [],
      loading: false,
      error: "",
      configurationOpen: loadConfigurationOpen(),
      statisticsOpen: false,
      statistics: {
        loading: false,
        error: "",
        metadata: null,
        topReviewers: [],
        topReviewedUsers: [],
        records: [],
        timeFilter: "all",
        excludeAutoReviewers: false,
        chartData: null,
      },
      reviewResults: {},
      runningReviews: {},
      runningBulkReview: false,
      diffs: {
        showDiffs: showDiffSetting,
        loadingDiff: [],
        diffHtml: [],
        showDiffsByPage: {}
      },
      searchQuery: "",
    });

    const forms = reactive({
      blockingCategories: "",
      autoApprovedGroups: "",
      oresDamagingThreshold: 0.0,
      oresGoodfaithThreshold: 0.0,
      oresDamagingThresholdLiving: 0.0,
      oresGoodfaithThresholdLiving: 0.0,
    });

    const currentWiki = computed(() =>
      state.wikis.find((wiki) => wiki.id === state.selectedWikiId) || null,
    );

    function matchesSearchQuery(page) {
      if (!state.searchQuery || state.searchQuery.trim() === "") {
        return true;
      }
      const query = state.searchQuery.toLowerCase().trim();

      // Check page title
      if (page.title) {
        const formattedTitle = formatTitle(page.title).toLowerCase().replace(/\s+/g, ' ');
        const normalizedQuery = query.replace(/\s+/g, ' ');
        if (formattedTitle.includes(normalizedQuery)) {
          return true;
        }
      }

      // Check revisions
      if (Array.isArray(page.revisions)) {
        for (const revision of page.revisions) {
          // Check timestamp
          if (revision.timestamp) {
            // Check raw timestamp
            if (revision.timestamp.toLowerCase().includes(query)) {
              return true;
            }
            // Check formatted timestamp as displayed in UI
            const formattedTimestamp = formatDateTime(revision.timestamp).toLowerCase();
            if (formattedTimestamp.includes(query)) {
              return true;
            }
          }
          // Check user_name
          if (revision.user_name && revision.user_name.toLowerCase().includes(query)) {
            return true;
          }
          // Check comment
          if (revision.comment && revision.comment.toLowerCase().includes(query)) {
            return true;
          }
          // Check change_tags
          if (Array.isArray(revision.change_tags)) {
            for (const tag of revision.change_tags) {
              if (tag && tag.toLowerCase().includes(query)) {
                return true;
              }
            }
          }
        }
      }

      return false;
    }

    const filteredPages = computed(() => {
      if (!state.searchQuery || state.searchQuery.trim() === "") {
        return state.pages;
      }
      return state.pages.filter((page) => matchesSearchQuery(page));
    });

    const visiblePages = computed(() => filteredPages.value.slice(0, pageDisplayLimit));

    const hasMorePages = computed(() => filteredPages.value.length > pageDisplayLimit);

    function saveDiffsToLocalStorage() {
      localStorage.setItem('showDiffsSetting', !state.diffs.showDiffs);
    }

    function syncForms() {
      if (!currentWiki.value) {
        forms.blockingCategories = "";
        forms.autoApprovedGroups = "";
        forms.oresDamagingThreshold = 0.0;
        forms.oresGoodfaithThreshold = 0.0;
        forms.oresDamagingThresholdLiving = 0.0;
        forms.oresGoodfaithThresholdLiving = 0.0;
        return;
      }
      forms.blockingCategories = (currentWiki.value.configuration.blocking_categories || []).join("\n");
      forms.autoApprovedGroups = (currentWiki.value.configuration.auto_approved_groups || []).join("\n");
      forms.oresDamagingThreshold = currentWiki.value.configuration.ores_damaging_threshold || 0.0;
      forms.oresGoodfaithThreshold = currentWiki.value.configuration.ores_goodfaith_threshold || 0.0;
      forms.oresDamagingThresholdLiving = currentWiki.value.configuration.ores_damaging_threshold_living || 0.0;
      forms.oresGoodfaithThresholdLiving = currentWiki.value.configuration.ores_goodfaith_threshold_living || 0.0;
    }

    async function apiRequest(url, options = {}) {
      state.error = "";
      try {
        const response = await fetch(url, options);
        if (!response.ok) {
          let message = response.statusText;
          try {
            const data = await response.json();
            if (data && data.error) {
              message = data.error;
            }
          } catch (error) {
            // Ignore JSON parsing errors.
          }
          throw new Error(message || "Unknown error");
        }
        return response.json();
      } catch (error) {
        state.error = error.message || "Request failed";
        throw error;
      }
    }

    async function fetchRevisionsForPage(wikiId, pageId) {
      try {
        const data = await apiRequest(`/api/wikis/${wikiId}/pages/${pageId}/revisions/`);
        return data.revisions || [];
      } catch (error) {
        return [];
      }
    }

    function resetReviewState() {
      state.reviewResults = {};
      state.runningReviews = {};
    }

    function setRunning(pageId, value) {
      state.runningReviews = { ...state.runningReviews, [pageId]: Boolean(value) };
    }

    function setReviewResults(pageId, results) {
      state.reviewResults = { ...state.reviewResults, [pageId]: results };
    }

    async function loadPending() {
      resetReviewState();
      if (!state.selectedWikiId) {
        state.pages = [];
        return;
      }
      state.loading = true;
      try {
        const wikiId = state.selectedWikiId;
        const data = await apiRequest(`/api/wikis/${wikiId}/pending/`);
        const pagesWithRevisions = await Promise.all(
          (data.pages || []).map(async (page) => {
            let revisions = Array.isArray(page.revisions) ? page.revisions : [];
            if (!revisions.length) {
              revisions = await fetchRevisionsForPage(wikiId, page.pageid);
            }
            return {
              ...page,
              revisions,
            };
          }),
        );
        if (wikiId === state.selectedWikiId) {
          state.pages = sortPages(pagesWithRevisions, state.sortOrder);
        }
      } catch (error) {
        state.pages = [];
      } finally {
        state.loading = false;
      }
    }

    async function refresh() {
      if (!state.selectedWikiId) {
        return;
      }
      state.loading = true;
      try {
        await apiRequest(`/api/wikis/${state.selectedWikiId}/refresh/`, {
          method: "POST",
        });
        await loadPending();
      } finally {
        state.loading = false;
      }
    }

    async function clearCache() {
      if (!state.selectedWikiId) {
        return;
      }
      state.loading = true;
      try {
        await apiRequest(`/api/wikis/${state.selectedWikiId}/clear/`, {
          method: "POST",
        });
        state.pages = [];
        resetReviewState();
      } finally {
        state.loading = false;
      }
    }

    function validateOresThreshold(value, name) {
      if (value === null || value === undefined || value === "") {
        return null;
      }
      const numValue = parseFloat(value);
      if (isNaN(numValue)) {
        return `${name} must be a valid number`;
      }
      if (numValue < 0.0 || numValue > 1.0) {
        return `${name} must be between 0.0 and 1.0`;
      }
      return null;
    }

    async function saveConfiguration() {
      if (!state.selectedWikiId) {
        return;
      }

      const validationErrors = [];
      const damagingError = validateOresThreshold(forms.oresDamagingThreshold, "Damaging threshold");
      if (damagingError) validationErrors.push(damagingError);

      const goodfaithError = validateOresThreshold(forms.oresGoodfaithThreshold, "Goodfaith threshold");
      if (goodfaithError) validationErrors.push(goodfaithError);

      const damagingLivingError = validateOresThreshold(forms.oresDamagingThresholdLiving, "Damaging threshold (Living persons)");
      if (damagingLivingError) validationErrors.push(damagingLivingError);

      const goodfaithLivingError = validateOresThreshold(forms.oresGoodfaithThresholdLiving, "Goodfaith threshold (Living persons)");
      if (goodfaithLivingError) validationErrors.push(goodfaithLivingError);

      if (validationErrors.length > 0) {
        state.error = validationErrors.join(". ");
        return;
      }

      const payload = {
        blocking_categories: parseTextarea(forms.blockingCategories),
        auto_approved_groups: parseTextarea(forms.autoApprovedGroups),
        ores_damaging_threshold: forms.oresDamagingThreshold,
        ores_goodfaith_threshold: forms.oresGoodfaithThreshold,
        ores_damaging_threshold_living: forms.oresDamagingThresholdLiving,
        ores_goodfaith_threshold_living: forms.oresGoodfaithThresholdLiving,
      };
      try {
        const data = await apiRequest(`/api/wikis/${state.selectedWikiId}/configuration/`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
        const wikiIndex = state.wikis.findIndex((wiki) => wiki.id === state.selectedWikiId);
        if (wikiIndex >= 0) {
          state.wikis[wikiIndex].configuration = data;
        }
        syncForms();
      } catch (error) {
        // Error already handled in apiRequest.
      }
    }

    function formatDate(value) {
      return formatDateTime(value);
    }

    function formatTitle(title) {
      if (!title) {
        return "";
      }
      return title.replace(/_/g, " ");
    }

    function getWikiOrigin() {
      const wiki = currentWiki.value;
      if (!wiki || !wiki.api_endpoint) {
        return "";
      }
      try {
        const apiUrl = new URL(wiki.api_endpoint);
        return apiUrl.origin;
      } catch (error) {
        return "";
      }
    }

    function buildLatestRevisionUrl(page) {
      if (!page || !page.title) {
        return "";
      }
      const normalizedTitle = page.title.replace(/ /g, "_");
      const encodedTitle = encodeURIComponent(normalizedTitle);
      const origin = getWikiOrigin();
      if (origin) {
        return `${origin}/wiki/${encodedTitle}`;
      }
      return `/wiki/${encodedTitle}`;
    }

    function buildRevisionDiffUrl(page, revision) {
      if (!revision || !revision.revid) {
        return "";
      }
      const params = new URLSearchParams({ diff: revision.revid });
      const parentId = Number(revision.parentid);
      if (!Number.isNaN(parentId) && parentId > 0) {
        params.set("oldid", parentId);
      } else if (page && page.stable_revid) {
        const stableId = Number(page.stable_revid);
        if (!Number.isNaN(stableId) && stableId > 0) {
          params.set("oldid", stableId);
        }
      }
      const origin = getWikiOrigin();
      const baseUrl = origin ? `${origin}/w/index.php` : "/w/index.php";
      return `${baseUrl}?${params.toString()}`;
    }

    function buildUserContributionsUrl(revision) {
      if (!revision || !revision.user_name) {
        return "";
      }
      const origin = getWikiOrigin();
      const normalized = revision.user_name.replace(/ /g, "_");
      const encoded = encodeURIComponent(normalized);
      if (origin) {
        return `${origin}/wiki/Special:Contributions/${encoded}`;
      }
      return `/wiki/Special:Contributions/${encoded}`;
    }

    function buildFlaggedRevsUrl(specialPage) {
      const origin = getWikiOrigin();
      if (!origin) {
        return "";
      }
      return `${origin}/wiki/Special:${specialPage}?uselang=en`;
    }

    function toggleConfiguration() {
      state.configurationOpen = !state.configurationOpen;
    }

    function toggleStatistics() {
      state.statisticsOpen = !state.statisticsOpen;
      if (state.statisticsOpen && state.statistics.topReviewers.length === 0) {
        loadStatistics();
      }
    }

    async function loadStatistics() {
      if (!state.selectedWikiId) {
        return;
      }
      state.statistics.loading = true;
      state.statistics.error = "";
      try {
        // Build query parameters
        const params = new URLSearchParams();
        if (state.statistics.timeFilter !== "all") {
          params.append("time_filter", state.statistics.timeFilter);
        }
        if (state.statistics.excludeAutoReviewers) {
          params.append("exclude_auto_reviewers", "true");
        }

        const url = `/api/wikis/${state.selectedWikiId}/statistics/?${params.toString()}`;
        const data = await fetch(url);
        if (!data.ok) {
          throw new Error(data.statusText || "Failed to load statistics");
        }
        const json = await data.json();
        state.statistics.metadata = json.metadata || null;
        state.statistics.topReviewers = json.top_reviewers || [];
        state.statistics.topReviewedUsers = json.top_reviewed_users || [];
        state.statistics.records = json.records || [];

        // Load chart data
        await loadChartData();
      } catch (error) {
        state.statistics.error = error.message || "Failed to load statistics";
        state.statistics.metadata = null;
        state.statistics.topReviewers = [];
        state.statistics.topReviewedUsers = [];
        state.statistics.records = [];
      } finally {
        state.statistics.loading = false;
      }
    }

    async function loadChartData() {
      if (!state.selectedWikiId) {
        return;
      }
      try {
        // Build query parameters
        const params = new URLSearchParams();
        if (state.statistics.timeFilter !== "all") {
          params.append("time_filter", state.statistics.timeFilter);
        }
        if (state.statistics.excludeAutoReviewers) {
          params.append("exclude_auto_reviewers", "true");
        }

        const url = `/api/wikis/${state.selectedWikiId}/statistics/charts/?${params.toString()}`;
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(response.statusText || "Failed to load chart data");
        }
        const json = await response.json();
        state.statistics.chartData = json;

        // Render charts after Vue updates the DOM
        setTimeout(() => renderCharts(), 100);
      } catch (error) {
        console.error("Failed to load chart data:", error);
      }
    }

    function setTimeFilter(filter) {
      state.statistics.timeFilter = filter;
      loadStatistics();
    }

    function renderCharts() {
      if (!state.statistics.chartData) {
        return;
      }

      const chartData = state.statistics.chartData;

      // Destroy existing charts
      Chart.helpers.each(Chart.instances, (instance) => {
        instance.destroy();
      });

      // Reviewers over time chart
      const reviewersCtx = document.getElementById("reviewersOverTimeChart");
      if (reviewersCtx) {
        new Chart(reviewersCtx, {
          type: "line",
          data: {
            labels: chartData.reviewers_over_time.map((d) => d.date),
            datasets: [
              {
                label: "Number of Reviewers",
                data: chartData.reviewers_over_time.map((d) => d.count),
                borderColor: "rgb(54, 162, 235)",
                backgroundColor: "rgba(54, 162, 235, 0.2)",
                tension: 0.1,
              },
            ],
          },
          options: {
            responsive: true,
            plugins: {
              title: {
                display: true,
                text: "Reviewers Over Time",
              },
            },
            scales: {
              y: {
                beginAtZero: true,
              },
            },
          },
        });
      }

      // Pending reviews per day chart
      const pendingCtx = document.getElementById("pendingReviewsChart");
      if (pendingCtx) {
        new Chart(pendingCtx, {
          type: "bar",
          data: {
            labels: chartData.pending_reviews_per_day.map((d) => d.date),
            datasets: [
              {
                label: "Reviews Per Day",
                data: chartData.pending_reviews_per_day.map((d) => d.count),
                borderColor: "rgb(75, 192, 192)",
                backgroundColor: "rgba(75, 192, 192, 0.6)",
              },
            ],
          },
          options: {
            responsive: true,
            plugins: {
              title: {
                display: true,
                text: "Pending Reviews Per Day",
              },
            },
            scales: {
              y: {
                beginAtZero: true,
              },
            },
          },
        });
      }

      // Average delay chart
      const avgDelayCtx = document.getElementById("averageDelayChart");
      if (avgDelayCtx) {
        new Chart(avgDelayCtx, {
          type: "line",
          data: {
            labels: chartData.average_delay_over_time.map((d) => d.date),
            datasets: [
              {
                label: "Average Delay (days)",
                data: chartData.average_delay_over_time.map((d) => d.avg_delay),
                borderColor: "rgb(255, 159, 64)",
                backgroundColor: "rgba(255, 159, 64, 0.2)",
                fill: true,
                tension: 0.1,
              },
            ],
          },
          options: {
            responsive: true,
            plugins: {
              title: {
                display: true,
                text: "Average Review Delay Over Time",
              },
            },
            scales: {
              y: {
                beginAtZero: true,
                title: {
                  display: true,
                  text: "Days",
                },
              },
            },
          },
        });
      }

      // Delay percentiles chart
      const percentilesCtx = document.getElementById("delayPercentilesChart");
      if (percentilesCtx) {
        new Chart(percentilesCtx, {
          type: "line",
          data: {
            labels: chartData.delay_percentiles.map((d) => d.date),
            datasets: [
              {
                label: "P10 (Lower Bound)",
                data: chartData.delay_percentiles.map((d) => d.p10),
                borderColor: "rgb(153, 102, 255)",
                backgroundColor: "rgba(153, 102, 255, 0.1)",
                fill: false,
                tension: 0.1,
              },
              {
                label: "P50 (Median)",
                data: chartData.delay_percentiles.map((d) => d.p50),
                borderColor: "rgb(255, 99, 132)",
                backgroundColor: "rgba(255, 99, 132, 0.2)",
                fill: "-1",
                tension: 0.1,
              },
              {
                label: "P90 (Upper Bound)",
                data: chartData.delay_percentiles.map((d) => d.p90),
                borderColor: "rgb(255, 205, 86)",
                backgroundColor: "rgba(255, 205, 86, 0.1)",
                fill: false,
                tension: 0.1,
              },
            ],
          },
          options: {
            responsive: true,
            plugins: {
              title: {
                display: true,
                text: "Review Delay Percentiles (P10, P50, P90)",
              },
            },
            scales: {
              y: {
                beginAtZero: true,
                title: {
                  display: true,
                  text: "Days",
                },
              },
            },
          },
        });
      }
    }

    async function refreshStatistics() {
      if (!state.selectedWikiId) {
        return;
      }
      state.statistics.loading = true;
      state.statistics.error = "";
      try {
        const response = await fetch(`/api/wikis/${state.selectedWikiId}/statistics/refresh/`, {
          method: "POST",
        });
        if (!response.ok) {
          throw new Error(response.statusText || "Failed to refresh statistics");
        }
        await loadStatistics();
      } catch (error) {
        state.statistics.error = error.message || "Failed to refresh statistics";
      } finally {
        state.statistics.loading = false;
      }
    }

    function buildUserPageUrl(username) {
      const origin = getWikiOrigin();
      if (!origin || !username) {
        return "";
      }
      const normalized = username.replace(/ /g, "_");
      const encoded = encodeURIComponent(normalized);
      return `${origin}/wiki/User:${encoded}`;
    }

    function buildPageUrl(pageTitle) {
      const origin = getWikiOrigin();
      if (!origin || !pageTitle) {
        return "";
      }
      const normalized = pageTitle.replace(/ /g, "_");
      const encoded = encodeURIComponent(normalized);
      return `${origin}/wiki/${encoded}`;
    }

    function buildPageDiffUrl(pageTitle, revisionId) {
      const origin = getWikiOrigin();
      if (!origin || !pageTitle || !revisionId) {
        return "";
      }
      const normalized = pageTitle.replace(/ /g, "_");
      const encoded = encodeURIComponent(normalized);
      return `${origin}/w/index.php?title=${encoded}&diff=prev&oldid=${revisionId}`;
    }

    async function runAutoreview(page, showDiffs=true) {
      if (!page || !state.selectedWikiId) {
        return;
      }
      const pageId = page.pageid;
      setRunning(pageId, true);
      try {
        const data = await apiRequest(
          `/api/wikis/${state.selectedWikiId}/pages/${pageId}/autoreview/`,
          {
            method: "POST",
          },
        );
        const mapping = {};
        (data.results || []).forEach((entry) => {
          if (entry && typeof entry.revid !== "undefined") {
            mapping[entry.revid] = entry;
          }
        });
        setReviewResults(pageId, mapping);
        if(showDiffs){
          showDiff(page)
        }
      } catch (error) {
        // Errors are surfaced via apiRequest state handling.
      } finally {
        setRunning(pageId, false);
      }
    }

    async function runAutoreviewAllVisible() {
      if (!state.selectedWikiId || state.runningBulkReview) {
        return;
      }
      const pages = visiblePages.value || [];
      if (!pages.length) {
        return;
      }
      const wikiId = state.selectedWikiId;
      state.runningBulkReview = true;
      try {
        for (const page of pages) {
          if (!page) {
            continue;
          }
          if (state.selectedWikiId !== wikiId) {
            break;
          }
          await runAutoreview(page, state.diffs.showDiffs);
        }
      } finally {
        state.runningBulkReview = false;
      }
    }

    function getRevisionReview(page, revision) {
      if (!page || !revision) {
        return null;
      }
      const pageResults = state.reviewResults[page.pageid];
      if (!pageResults) {
        return null;
      }
      return pageResults[revision.revid] || null;
    }

    function isAutoreviewRunning(page) {
      if (!page) {
        return false;
      }
      return Boolean(state.runningReviews[page.pageid]);
    }

    function formatTestStatus(status) {
      if (status === "ok") {
        return "OK";
      }
      if (status === "fail") {
        return "FAIL";
      }
      if (status === "not_ok") {
        return "Neutral";
      }
      return status || "";
    }

    function statusTagClass(status) {
      if (status === "ok") {
        return "is-success";
      }
      if (status === "fail") {
        return "is-danger";
      }
      if (status === "not_ok") {
        return "is-warning";
      }
      return "is-light";
    }

    function formatDecision(decision) {
      if (!decision) {
        return "";
      }
      const label = decision.label || decision.status || "";
      const reason = decision.reason ? ` – ${decision.reason}` : "";
      const base = `${label}${reason}`.trim();
      if (!base) {
        return "(dry-run)";
      }
      return `${base} (dry-run)`;
    }


    /**
     * This functions gets Html to render for each revision
     * @param {*} page - this is the page that has revision
     */

    async function showDiff(page) {

      page.revisions.forEach(async (revision)=> {
        state.diffs.loadingDiff[revision.revid] = true;
        // when running autoreview all
        // add show checkbox for all auto review is checked
        // update individual page checkbox to true
        if(state.diffs.showDiffs){
          state.diffs.showDiffsByPage[page.pageid]=true
        }
        try {
          const title = page.title;
          const oldid = revision.parentid;
          const diffid = revision.revid;

          const baseUrl = "https://fi.wikipedia.org";
          const diffUrl = `${baseUrl}/w/index.php?title=${title}&diff=${diffid}&oldid=${oldid}&action=render&diffonly=1&uselang=en`;

          const apiUrl = `/api/wikis/fetch-diff/?url=${encodeURIComponent(diffUrl)}`;
          const response = await fetch(apiUrl);

          const html = await response.text();

          // inject href to point to Wikipedia domain name(base url).
          // form view all pending changes.
          // where there are multiple revisions.
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, 'text/html');
          const link = doc.querySelector(`a[title="${formatTitle(title)}"]`);

          if (link) {
              const relativeHref = link.getAttribute('href');
              const domainUrl = "//fi.wikipedia.org";

              if (relativeHref && relativeHref.startsWith('/w/')) {
                  link.setAttribute('href', `${domainUrl}${relativeHref}`);
              }
          }

          const updatedHtml = doc.body.innerHTML;
          state.diffs.diffHtml[revision.revid] = updatedHtml;

        } catch (error) {
          state.diffs.diffHtml = `<p class="has-text-danger">Failed to load diff</p>`;
        } finally {
          state.diffs.loadingDiff[revision.revid] = false;
        }

      })
    }

    watch(
      () => state.configurationOpen,
      (newValue) => {
        persistConfigurationOpen(newValue);
      },
      { immediate: true },
    );

    watch(
      () => state.selectedWikiId,
      (newValue) => {
        persistSelectedWikiId(newValue);
        resetReviewState();
      },
      { immediate: true },
    );

    watch(
      () => state.sortOrder,
      (newValue) => {
        state.pages = sortPages(state.pages, newValue);
        persistSortOrder(newValue);
      },
      { immediate: true },
    );

    watch(currentWiki, () => {
      syncForms();
      loadPending();
      // Reload statistics if statistics panel is open
      if (state.statisticsOpen) {
        loadStatistics();
      }
    }, { immediate: true });

    onMounted(() => {
      syncForms();
      // If on statistics page and have a wiki selected, load statistics for wiki
      if (window.location.pathname.includes('/statistics/') && state.selectedWikiId) {
        loadStatistics();
      }
    });

    return {
      state,
      forms,
      currentWiki,
      filteredPages,
      visiblePages,
      hasMorePages,
      pageDisplayLimit,
      refresh,
      clearCache,
      saveConfiguration,
      loadPending,
      formatDate,
      formatDateTime,
      toggleConfiguration,
      toggleStatistics,
      loadStatistics,
      refreshStatistics,
      setTimeFilter,
      formatTitle,
      buildLatestRevisionUrl,
      buildRevisionDiffUrl,
      buildUserContributionsUrl,
      buildUserPageUrl,
      buildPageUrl,
      buildPageDiffUrl,
      buildFlaggedRevsUrl,
      runAutoreview,
      runAutoreviewAllVisible,
      getRevisionReview,
      isAutoreviewRunning,
      formatTestStatus,
      statusTagClass,
      formatDecision,
      saveDiffsToLocalStorage,
    };
  },
}).mount("#app");
