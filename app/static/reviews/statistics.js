// Vue 3 Composition API for Statistics Page
const { createApp, reactive, computed, onMounted, watch, nextTick } = Vue;

// Get initial wiki data from Django template
const wikisDataElement = document.getElementById('wikis-data');
const AVAILABLE_WIKIS = wikisDataElement ? JSON.parse(wikisDataElement.textContent) : [];

createApp({
  setup() {
    const state = reactive({
      // Data
      tableData: [],
      loading: false,
      error: null,

      // Chart
      chart: null,

      // Filters
      selectedWikis: [],
      series: {
        pendingLag_average: true,
        totalPages_ns0: true,
        reviewedPages_ns0: true,
        syncedPages_ns0: true,
        pendingChanges: true,
        number_of_reviewers: true,
        number_of_reviews: true,
        reviews_per_reviewer: true,
      },

      // Date filters (future feature)
      startDate: null,
      endDate: null,

      // View modes
      viewMode: 'both', // 'chart', 'table', 'both', 'separate'

      // UI state
      lastUpdated: null,
    });

    // Initialize with default wiki if none selected
    if (state.selectedWikis.length === 0 && AVAILABLE_WIKIS.length > 0) {
      const defaultWiki = AVAILABLE_WIKIS.find(w => w.code === 'fi') || AVAILABLE_WIKIS[0];
      state.selectedWikis = [defaultWiki.code];
    }

    // Computed properties
    const availableWikis = computed(() => AVAILABLE_WIKIS);

    const filteredTableData = computed(() => {
      return state.tableData.filter(entry => {
        if (state.selectedWikis.length > 0 && !state.selectedWikis.includes(entry.wiki)) {
          return false;
        }
        return true;
      });
    });

    const enabledSeries = computed(() => {
      const seriesConfig = [
        { key: "pendingLag_average", label: "Pending Lag (Average)" },
        { key: "totalPages_ns0", label: "Total Pages (NS:0)" },
        { key: "reviewedPages_ns0", label: "Reviewed Pages (NS:0)" },
        { key: "syncedPages_ns0", label: "Synced Pages (NS:0)" },
        { key: "pendingChanges", label: "Pending Changes" },
        { key: "number_of_reviewers", label: "Number of Reviewers" },
        { key: "number_of_reviews", label: "Number of Reviews" },
        { key: "reviews_per_reviewer", label: "Reviews Per Reviewer" },
      ];

      return seriesConfig.filter(series => state.series[series.key]);
    });

    // Chart management
    function initializeChart() {
      const ctx = document.getElementById("statisticsChart");
      if (!ctx) return;

      if (state.chart) {
        state.chart.destroy();
      }

      state.chart = new Chart(ctx, {
        type: "line",
        data: {
          labels: [],
          datasets: [],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            title: {
              display: true,
              text: "FlaggedRevs Statistics Over Time",
            },
            legend: {
              display: true,
              position: "top",
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

    function updateChart() {
      console.log("updateChart called - tableData length:", state.tableData.length);

      if (state.tableData.length === 0) {
        console.log("No data to display");
        return;
      }

      // Destroy existing chart to avoid reactivity issues
      if (state.chart) {
        state.chart.destroy();
        state.chart = null;
      }

      // Make a simple copy of data to avoid reactivity issues
      const data = JSON.parse(JSON.stringify(state.tableData));
      const selectedWikis = [...state.selectedWikis];

      console.log("Raw data:", data);
      console.log("Selected wikis:", selectedWikis);

      // Get unique dates
      const labels = [...new Set(data.map(d => d.date))].sort();
      console.log("Labels:", labels);

      // Build datasets
      const datasets = [];
      const colors = ["#3273dc", "#48c774", "#ffdd57", "#f14668", "#00d1b2", "#ff3860", "#209cee", "#ff6348"];
      let colorIndex = 0;

      const seriesConfig = [
        { key: "pendingLag_average", label: "Pending Lag (Average)" },
        { key: "totalPages_ns0", label: "Total Pages (NS:0)" },
        { key: "reviewedPages_ns0", label: "Reviewed Pages (NS:0)" },
        { key: "syncedPages_ns0", label: "Synced Pages (NS:0)" },
        { key: "pendingChanges", label: "Pending Changes" },
        { key: "number_of_reviewers", label: "Number of Reviewers" },
        { key: "number_of_reviews", label: "Number of Reviews" },
        { key: "reviews_per_reviewer", label: "Reviews Per Reviewer" },
      ];

      selectedWikis.forEach(wiki => {
        console.log("Processing wiki:", wiki);
        seriesConfig.forEach(series => {
          console.log("Processing series:", series.key, "enabled:", state.series[series.key]);
          if (!state.series[series.key]) return;

          const seriesData = labels.map(date => {
            const entry = data.find(d => d.wiki === wiki && d.date === date);
            return entry ? (entry[series.key] || 0) : null;
          });

          console.log(`Data for ${wiki} - ${series.key}:`, seriesData);

          if (seriesData.some(val => val !== null && val !== undefined)) {
            datasets.push({
              label: `${wiki} - ${series.label}`,
              data: seriesData,
              borderColor: colors[colorIndex % colors.length],
              backgroundColor: colors[colorIndex % colors.length] + "20",
              tension: 0.1,
              fill: false,
            });
            colorIndex++;
            console.log(`Added dataset for ${wiki} - ${series.key}`);
          }
        });
      });

      console.log("Final datasets:", datasets);
      console.log("Creating new chart with", datasets.length, "datasets");

      // Only update main chart if we're in chart or both mode
      if (state.viewMode !== 'chart' && state.viewMode !== 'both') {
        console.log("Skipping main chart update - view mode is", state.viewMode);
        return;
      }

      // Create a completely new chart instead of updating
      const ctx = document.getElementById("statisticsChart");
      if (!ctx) {
        console.error("Chart canvas not found");
        return;
      }

      state.chart = new Chart(ctx, {
        type: "line",
        data: {
          labels: labels,
          datasets: datasets,
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            title: {
              display: true,
              text: "FlaggedRevs Statistics Over Time",
            },
            legend: {
              display: true,
              position: "top",
            },
          },
          scales: {
            y: {
              type: 'logarithmic',
              beginAtZero: false,
              min: 1,
              title: {
                display: true,
                text: 'Values (Logarithmic Scale)'
              }
            },
          },
        },
      });

      console.log("New chart created successfully");
    }

    function createSeparateCharts() {
      console.log("createSeparateCharts called. Current viewMode:", state.viewMode);
      console.log("state.series:", state.series);
      console.log("enabledSeries:", enabledSeries.value);
      console.log("tableData length:", state.tableData.length);

      // Debug: Check if any canvas elements exist
      const allCanvases = document.querySelectorAll('canvas');
      console.log("Total canvas elements found:", allCanvases.length);
      allCanvases.forEach((canvas, index) => {
        console.log(`Canvas ${index}:`, canvas.id, canvas);
      });

      // Destroy existing separate charts
      enabledSeries.value.forEach(series => {
        const chartId = `chart-${series.key}`;
        const existingChart = Chart.getChart(chartId);
        if (existingChart) {
          existingChart.destroy();
        }
      });

      if (state.tableData.length === 0) {
        console.log("No table data available for separate charts");
        return;
      }

      // Create data copy to avoid reactivity issues
      const data = JSON.parse(JSON.stringify(state.tableData));
      const selectedWikis = [...state.selectedWikis];

      // Get unique dates
      const labels = [...new Set(data.map(d => d.date))].sort();
      const colors = ["#3273dc", "#48c774", "#ffdd57", "#f14668", "#00d1b2", "#ff3860", "#209cee", "#ff6348"];

      enabledSeries.value.forEach((series, index) => {
        const canvasId = `chart-${series.key}`;
        console.log(`Attempting to find canvas for ID: ${canvasId}`);
        const ctx = document.getElementById(canvasId);
        console.log(`Creating chart for ${series.key}, canvas found:`, !!ctx);
        if (!ctx) {
          console.log(`Canvas not found for ${series.key}`);
          return;
        }

        const datasets = [];
        let colorIndex = 0;

        selectedWikis.forEach(wiki => {
          const seriesData = labels.map(date => {
            const entry = data.find(d => d.wiki === wiki && d.date === date);
            return entry ? (entry[series.key] || 0) : null;
          });

          if (seriesData.some(val => val !== null && val !== undefined)) {
            datasets.push({
              label: wiki,
              data: seriesData,
              borderColor: colors[colorIndex % colors.length],
              backgroundColor: colors[colorIndex % colors.length] + "20",
              tension: 0.1,
              fill: false,
            });
            colorIndex++;
          }
        });

        new Chart(ctx, {
          type: "line",
          data: {
            labels: labels,
            datasets: datasets,
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: series.label,
              },
              legend: {
                display: true,
                position: "top",
              },
            },
            scales: {
              y: {
                type: 'logarithmic',
                beginAtZero: false,
                min: 1,
              },
            },
          },
        });
      });
    }

    // Data loading
    async function loadData() {
      if (state.loading) return;

      state.loading = true;
      state.error = null;

      try {
        const promises = [];

        // Build URL parameters for API calls
        const apiParams = new URLSearchParams();
        if (state.startDate) {
          apiParams.set('start_date', state.startDate);
        }
        if (state.endDate) {
          apiParams.set('end_date', state.endDate);
        }
        const queryString = apiParams.toString();

        // Load statistics for each selected wiki
        for (const wiki of state.selectedWikis) {
          const statsUrl = `/api/statistics/?wiki=${wiki}${queryString ? '&' + queryString : ''}`;
          promises.push(
            fetch(statsUrl)
              .then(response => response.json())
          );

          // Load review activity (stretch goal)
          const activityUrl = `/api/review-activity/?wiki=${wiki}${queryString ? '&' + queryString : ''}`;
          promises.push(
            fetch(activityUrl)
              .then(response => response.json())
          );
        }

        const results = await Promise.all(promises);

        // Process results
        const allData = [];
        for (let i = 0; i < results.length; i += 2) {
          const statsData = results[i];
          const activityData = results[i + 1];

          // Merge statistics and activity data
          const wikiData = {};

          // Add statistics data
          if (statsData.data) {
            statsData.data.forEach(entry => {
              const key = `${entry.wiki}-${entry.date}`;
              if (!wikiData[key]) {
                wikiData[key] = { ...entry };
              }
            });
          }

          // Add activity data
          if (activityData.data) {
            activityData.data.forEach(entry => {
              const key = `${entry.wiki}-${entry.date}`;
              if (!wikiData[key]) {
                wikiData[key] = { ...entry };
              } else {
                Object.assign(wikiData[key], entry);
              }
            });
          }

          // Convert to array
          allData.push(...Object.values(wikiData));
        }

        console.log("All merged data:", allData);
        state.tableData = allData;
        state.lastUpdated = new Date();

        console.log("State tableData set to:", state.tableData);

        // Update chart after a small delay to avoid reactivity issues
        setTimeout(async () => {
          console.log("Timeout reached, calling chart update");
          if (state.viewMode === 'separate') {
            // Wait for Vue to update the DOM with new canvas elements
            await nextTick();
            setTimeout(() => {
              createSeparateCharts();
            }, 100);
          } else {
            updateChart();
          }
        }, 100);

      } catch (error) {
        state.error = error.message;
        console.error('Error loading data:', error);
      } finally {
        state.loading = false;
      }
    }

    async function refreshData() {
      await loadData();
    }

    // URL management
    function updateUrl() {
      const params = new URLSearchParams();

      // Handle wiki selection
      if (state.selectedWikis.length === 1) {
        // Single wiki - use 'wiki' parameter
        params.set('wiki', state.selectedWikis[0]);
      } else if (state.selectedWikis.length > 1) {
        // Multiple wikis - use 'db' parameter
        params.set('db', state.selectedWikis.join(','));
      }

      // Handle data series selection
      const enabledSeries = Object.entries(state.series)
        .filter(([key, enabled]) => enabled)
        .map(([key]) => key);

      if (enabledSeries.length > 0 && enabledSeries.length < Object.keys(state.series).length) {
        // Only add frs_key if not all series are selected
        params.set('frs_key', enabledSeries.join(','));
      }

      // Handle view mode
      if (state.viewMode !== 'both') {
        params.set('view', state.viewMode);
      }

      // Handle yearmonth parameter
      if (state.startDate && state.endDate) {
        const startDate = new Date(state.startDate);
        const endDate = new Date(state.endDate);
        // Check if it's the same month
        if (startDate.getFullYear() === endDate.getFullYear() &&
            startDate.getMonth() === endDate.getMonth() &&
            startDate.getDate() === 1 && endDate.getDate() >= 28) {
          const yearmonth = `${startDate.getFullYear()}${String(startDate.getMonth() + 1).padStart(2, '0')}`;
          params.set('yearmonth', yearmonth);
        }
      }

      const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
      window.history.replaceState({}, '', newUrl);
    }

    // Load URL parameters on mount
    function loadUrlParams() {
      const params = new URLSearchParams(window.location.search);

      // Handle 'db' parameter (multiple wikis)
      const dbParam = params.get('db');
      if (dbParam) {
        state.selectedWikis = dbParam.split(',').filter(w =>
          AVAILABLE_WIKIS.some(aw => aw.code === w)
        );
      }

      // Handle 'wiki' parameter (single wiki - overrides 'db')
      const wikiParam = params.get('wiki');
      if (wikiParam) {
        const wiki = AVAILABLE_WIKIS.find(aw => aw.code === wikiParam);
        if (wiki) {
          state.selectedWikis = [wikiParam];
        }
      }

      // Handle 'frs_key' parameter (specific data series)
      const frsKeyParam = params.get('frs_key');
      if (frsKeyParam) {
        // Reset all series
        Object.keys(state.series).forEach(key => {
          state.series[key] = false;
        });

        // Enable selected series
        frsKeyParam.split(',').forEach(key => {
          if (state.series.hasOwnProperty(key)) {
            state.series[key] = true;
          }
        });
      }

      // Handle 'yearmonth' parameter (single month view)
      const yearmonthParam = params.get('yearmonth');
      if (yearmonthParam) {
        // Set view mode to table only for single month
        state.viewMode = 'table';
        // Parse yearmonth (e.g., "202012" -> "2020-12")
        const year = yearmonthParam.substring(0, 4);
        const month = yearmonthParam.substring(4, 6);
        state.startDate = `${year}-${month}-01`;
        state.endDate = `${year}-${month}-31`;
      }

      // Handle 'view' parameter
      const viewParam = params.get('view');
      if (viewParam && ['chart', 'table', 'both', 'separate'].includes(viewParam)) {
        state.viewMode = viewParam;
      }
    }

    // Watchers
    watch(() => state.selectedWikis, () => {
      updateUrl();
      loadData();
    }, { deep: true });

    watch(() => state.series, () => {
      updateUrl();
      // Trigger appropriate chart rendering when series change
      setTimeout(() => {
        if (state.viewMode === 'separate') {
          createSeparateCharts();
        } else {
          updateChart();
        }
      }, 100);
    }, { deep: true });

    watch(() => state.viewMode, async () => {
      updateUrl();
      // Trigger appropriate chart rendering when view mode changes
      if (state.viewMode === 'separate') {
        // Wait for Vue to update the DOM with new canvas elements
        await nextTick();
        setTimeout(() => {
          createSeparateCharts();
        }, 500);  // Increased timeout to give Vue more time to render
      } else {
        updateChart();
      }
    });

    // Lifecycle
    onMounted(() => {
      initializeChart();
      loadUrlParams();
      loadData();

      // Add resize listener to ensure chart renders properly
      window.addEventListener('resize', () => {
        if (state.chart) {
          state.chart.resize();
        }
      });
    });

    return {
      state,
      availableWikis,
      enabledSeries,
      filteredTableData,
      loadData,
      refreshData,
      updateUrl,
    };
  }
}).mount('#app');
