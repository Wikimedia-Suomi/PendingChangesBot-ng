// Vue 3 Composition API for Statistics Page
const { createApp, reactive, computed, onMounted, watch } = Vue;

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

    // Data loading
    async function loadData() {
      if (state.loading) return;

      state.loading = true;
      state.error = null;

      try {
        const promises = [];

        // Load statistics for each selected wiki
        for (const wiki of state.selectedWikis) {
          promises.push(
            fetch(`/api/statistics/?wiki=${wiki}`)
              .then(response => response.json())
          );

          // Load review activity (stretch goal)
          promises.push(
            fetch(`/api/review-activity/?wiki=${wiki}`)
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
        setTimeout(() => {
          console.log("Timeout reached, calling updateChart");
          updateChart();
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

      if (state.selectedWikis.length > 0) {
        params.set('db', state.selectedWikis.join(','));
      }

      const enabledSeries = Object.entries(state.series)
        .filter(([key, enabled]) => enabled)
        .map(([key]) => key);

      if (enabledSeries.length > 0) {
        params.set('frs_key', enabledSeries.join(','));
      }

      const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
      window.history.replaceState({}, '', newUrl);
    }

    // Load URL parameters on mount
    function loadUrlParams() {
      const params = new URLSearchParams(window.location.search);

      const dbParam = params.get('db');
      if (dbParam) {
        state.selectedWikis = dbParam.split(',').filter(w =>
          AVAILABLE_WIKIS.some(aw => aw.code === w)
        );
      }

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
    }

    // Watchers
    watch(() => state.selectedWikis, () => {
      updateUrl();
      loadData();
    }, { deep: true });

    watch(() => state.series, () => {
      updateUrl();
      updateChart();
    }, { deep: true });

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
      filteredTableData,
      loadData,
      refreshData,
      updateUrl,
    };
  }
}).mount('#app');
