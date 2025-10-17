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
      lastUpdated: null, // Timestamp of last data refresh

      // Chart
      chart: null,
      singleChart: null, // For FRS Key mode single chart

      // Filters
      selectedWikis: [],
      filterMode: 'wiki', // 'wiki', 'frs_key', 'yearmonth'
      selectedFrsKey: 'pendingLag_average', // Default FRS key selection
      selectedWikiForTable: 'fi', // Default wiki for table display
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

      // Month selection
      selectedMonth: '',
      availableMonths: [],

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

      // Always show all series
      return seriesConfig;
    });

    const isSingleMonthView = computed(() => {
      // Single month view when a specific month is selected and multiple wikis are available
      return state.selectedMonth !== '' && state.selectedWikis.length > 1;
    });

    const singleMonthData = computed(() => {
      if (!isSingleMonthView.value) return [];

      // Group data by wiki and create a single row per wiki
      const wikiData = {};
      state.tableData.forEach(entry => {
        if (!wikiData[entry.wiki]) {
          wikiData[entry.wiki] = {
            wiki: entry.wiki,
            date: entry.date,
            ...entry
          };
        }
      });

      return Object.values(wikiData).sort((a, b) => a.wiki.localeCompare(b.wiki));
    });

    const yearMonthTableData = computed(() => {
      if (state.filterMode !== 'yearmonth') return [];

      // Group data by wiki for the selected month
      const wikiData = {};
      state.tableData.forEach(entry => {
        if (!wikiData[entry.wiki]) {
          wikiData[entry.wiki] = {
            wiki: entry.wiki,
            pendingLag_average: entry.pendingLag_average || 0,
            totalPages_ns0: entry.totalPages_ns0 || 0,
            reviewedPages_ns0: entry.reviewedPages_ns0 || 0,
            syncedPages_ns0: entry.syncedPages_ns0 || 0,
            pendingChanges: entry.pendingChanges || 0,
            number_of_reviewers: entry.number_of_reviewers || 0,
            number_of_reviews: entry.number_of_reviews || 0,
            reviews_per_reviewer: entry.reviews_per_reviewer || 0,
          };
        }
      });

      return Object.values(wikiData).sort((a, b) => a.wiki.localeCompare(b.wiki));
    });

    const yearMonthTableTitle = computed(() => {
      if (state.filterMode !== 'yearmonth' || !state.tableData.length) return 'YearMonth Data';

      // Get the date from the first entry and format as YYYYMM
      const firstDate = state.tableData[0]?.date;
      if (firstDate) {
        return firstDate.replace('-', '').substring(0, 6); // Convert 2023-10-01 to 202310
      }
      return 'YearMonth Data';
    });

    // FRS Key table computed properties
    const selectedFrsKeyLabel = computed(() => {
      const seriesConfig = {
        pendingLag_average: "Pending Lag (Average)",
        totalPages_ns0: "Total Pages (NS:0)",
        reviewedPages_ns0: "Reviewed Pages (NS:0)",
        syncedPages_ns0: "Synced Pages (NS:0)",
        pendingChanges: "Pending Changes",
        number_of_reviewers: "Number of Reviewers",
        number_of_reviews: "Number of Reviews",
        reviews_per_reviewer: "Reviews Per Reviewer",
      };
      return seriesConfig[state.selectedFrsKey] || state.selectedFrsKey;
    });

    const frsKeyTableDates = computed(() => {
      if (state.filterMode !== 'frs_key' || !state.tableData.length) return [];

      // Get unique dates and format them as YYYYMM
      const dates = [...new Set(state.tableData.map(d => d.date))].sort();
      return dates.map(date => {
        // Convert 2023-10-01 to 202310
        return date.replace('-', '').substring(0, 6);
      });
    });

    // Wiki table data for the selected wiki only
    const wikiTableData = computed(() => {
      if (state.filterMode !== 'wiki' || !state.tableData.length) return [];

      // Filter data for the selected wiki only
      return state.tableData
        .filter(entry => entry.wiki === state.selectedWikiForTable)
        .sort((a, b) => a.date.localeCompare(b.date));
    });

    // Formatted last updated timestamp
    const lastUpdatedFormatted = computed(() => {
      if (!state.lastUpdated) return 'Never';

      const date = new Date(state.lastUpdated);
      const now = new Date();
      const diffMs = now - date;
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

      if (diffMinutes < 1) return 'Just now';
      if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`;
      if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
      if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;

      return date.toLocaleString();
    });

    // Method to get FRS Key value for a specific wiki and date
    function getFrsKeyValue(wiki, date) {
      // Convert YYYYMM back to YYYY-MM-DD format for lookup
      const year = date.substring(0, 4);
      const month = date.substring(4, 6);
      const lookupDate = `${year}-${month}-01`;

      const entry = state.tableData.find(d => d.wiki === wiki && d.date === lookupDate);
      if (!entry) return 'N/A';

      const value = entry[state.selectedFrsKey];
      if (value === null || value === undefined) return 'N/A';

      // Format based on data type
      if (state.selectedFrsKey === 'pendingLag_average' || state.selectedFrsKey === 'reviews_per_reviewer') {
        return value.toFixed(1);
      } else if (state.selectedFrsKey.includes('Pages') || state.selectedFrsKey === 'pendingChanges') {
        return value.toLocaleString();
      } else {
        return value.toString();
      }
    }

    // Chart management
    function initializeChart() {
      const ctx = document.getElementById("statisticsChart");
      if (!ctx) {
        return;
      }

      // Check if canvas has valid context
      try {
        const context = ctx.getContext('2d');
        if (!context) {
          return;
        }
      } catch (error) {
        return;
      }

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
      console.log('=== CHART UPDATE DEBUG ===');
      console.log('updateChart called, filterMode:', state.filterMode);
      console.log('selectedWikis:', state.selectedWikis);
      console.log('tableData length:', state.tableData.length);

      if (state.tableData.length === 0) {
        console.log('No table data - destroying existing charts');
        // Destroy existing charts when no data
        if (state.charts) {
          Object.values(state.charts).forEach(chart => {
            if (chart) {
              chart.destroy();
            }
          });
          state.charts = {};
        }
        return;
      }

      // Destroy existing charts to avoid reactivity issues
      if (state.charts) {
        Object.values(state.charts).forEach(chart => {
          if (chart) {
            chart.destroy();
          }
        });
        state.charts = {};
      }
      if (state.chart) {
        state.chart.destroy();
        state.chart = null;
      }


      // Make a simple copy of data to avoid reactivity issues
      const data = JSON.parse(JSON.stringify(state.tableData));
      const selectedWikis = [...state.selectedWikis];

      // Get unique dates
      const labels = [...new Set(data.map(d => d.date.substring(0, 4)))].sort();

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

      // Create separate charts for each data series when in Wiki mode
      if (state.filterMode === 'wiki') {
        console.log('=== WIKI MODE CHART CREATION DEBUG ===');
        console.log('Creating separate charts for Wiki mode');
        console.log('enabledSeries:', enabledSeries.value);
        console.log('selectedWikis:', state.selectedWikis);
        console.log('tableData length:', state.tableData.length);

        // Hide any existing no-data message
        const wikiChartsSection = document.querySelector('section[v-show="state.filterMode === \'wiki\'"]');
        if (wikiChartsSection) {
          const existingMessage = wikiChartsSection.querySelector('.wiki-no-data-message');
          if (existingMessage) {
            existingMessage.remove();
          }
        }
        seriesConfig.forEach((series, seriesIndex) => {
          const canvasId = `chart-${series.key}`;
          const ctx = document.getElementById(canvasId);
          console.log(`Looking for canvas: ${canvasId}, found:`, ctx);
          if (!ctx) {
            console.log(`Canvas ${canvasId} not found, skipping`);
            return;
          }

          const datasets = [];
          let colorIndex = 0;

          selectedWikis.forEach(wiki => {
            const seriesData = labels.map(year => {
              // Find all entries for this wiki and year, then take the latest one
              const yearEntries = data.filter(d => d.wiki === wiki && d.date.startsWith(year));
              const latestEntry = yearEntries.sort((a, b) => b.date.localeCompare(a.date))[0];
              return latestEntry ? (latestEntry[series.key] || null) : null;
            });

            // Debug Pending Lag data specifically
            if (series.key === 'pendingLag_average') {
              console.log(`${wiki}wiki_p Pending Lag data:`, seriesData);
              console.log(`${wiki}wiki_p non-null values:`, seriesData.filter(val => val !== null && val !== undefined));
            }

            if (seriesData.some(val => val !== null && val !== undefined)) {
              datasets.push({
                label: `${wiki}wiki_p`,
                data: seriesData,
                borderColor: colors[colorIndex % colors.length],
                backgroundColor: colors[colorIndex % colors.length] + "20",
                tension: 0.4,
                pointRadius: 0,
                fill: false,
              });
              colorIndex++;
            }
          });

          if (!state.charts) state.charts = {};
          console.log(`Creating chart for ${series.label} with ${datasets.length} datasets`);
          console.log('selectedWikis for this chart:', selectedWikis);

          // If no datasets available, show a message instead of creating an empty chart
          if (datasets.length === 0) {
            console.log(`No datasets available for ${series.label} - showing no data message`);
            // Clear any existing chart
            if (state.charts[series.key]) {
              state.charts[series.key].destroy();
              state.charts[series.key] = null;
            }

            // Show a message in the canvas area
            ctx.style.display = 'none';

            // Create a message element if it doesn't exist
            let messageEl = ctx.parentElement.querySelector('.no-data-message');
            if (!messageEl) {
              messageEl = document.createElement('div');
              messageEl.className = 'no-data-message';
              messageEl.style.cssText = `
                display: flex;
                align-items: center;
                justify-content: center;
                height: 300px;
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                color: #6c757d;
                font-size: 16px;
                text-align: center;
                padding: 20px;
              `;
              messageEl.innerHTML = `
                <div>
                  <strong>No data available</strong><br>
                  The selected wikis (${selectedWikis.map(w => `${w}wiki_p`).join(', ')})
                  have no data for "${series.label}".
                </div>
              `;
              ctx.parentElement.appendChild(messageEl);
            }
            messageEl.style.display = 'flex';
            return;
          }

          // Hide any existing no-data message
          const messageEl = ctx.parentElement.querySelector('.no-data-message');
          if (messageEl) {
            messageEl.style.display = 'none';
          }
          ctx.style.display = 'block';

          state.charts[series.key] = new Chart(ctx, {
            type: 'line',
            data: {
              labels: labels,
              datasets: datasets,
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              animation: {
                duration: 750
              },
              interaction: {
                intersect: false,
                mode: 'index'
              },
              plugins: {
                title: {
                  display: true,
                  text: series.label,
                },
                legend: {
                  display: true,
                  position: 'top',
                },
              },
              scales: {
                x: {
                  type: 'category',
                  border: {
                    display: true,
                    color: '#000',
                    width: 2,
                  },
                  grid: {
                    display: true,
                    color: 'rgba(0, 0, 0, 0.05)',
                  },
                  ticks: {
                    maxRotation: 0,
                    minRotation: 0,
                    autoSkip: true,
                    callback: function(value, index, ticks) {
                      // Extract year from the date string
                      const dateStr = this.getLabelForValue(value);
                      if (dateStr) {
                        const year = dateStr.split('-')[0];
                        // Only show year for the first occurrence of each year
                        if (index === 0) {
                          return year;
                        }
                        // Check if this year is different from the previous tick's year
                        const prevDateStr = this.getLabelForValue(ticks[index - 1].value);
                        const prevYear = prevDateStr ? prevDateStr.split('-')[0] : '';
                        if (year !== prevYear) {
                          return year;
                        }
                        return '';
                      }
                      return '';
                    },
                  },
                },
                y: {
                  beginAtZero: true,
                  border: {
                    display: true,
                    color: '#000',
                    width: 2,
                  },
                  grid: {
                    display: true,
                    color: 'rgba(0, 0, 0, 0.05)',
                  },
                  ticks: {
                    callback: function(value) {
                      return value.toLocaleString();
                    },
                  },
                },
              },
            },
          });
        });
      }

      // Only update main chart if we're in chart or both mode
      if (state.viewMode !== 'chart' && state.viewMode !== 'both') {
        return;
      }

      // Create a completely new chart instead of updating
      const ctx = document.getElementById("statisticsChart");
      if (!ctx) {
        return;
      }

      // Check if canvas has valid context
      try {
        const context = ctx.getContext('2d');
        if (!context) {
          return;
        }
      } catch (error) {
        return;
      }

      try {
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
      } catch (error) {
        // Chart creation failed, skip silently
        return;
      }
    }

    function createSeparateCharts() {

      // Destroy existing separate charts
      enabledSeries.value.forEach(series => {
        const chartId = `chart-${series.key}`;
        const existingChart = Chart.getChart(chartId);
        if (existingChart) {
          existingChart.destroy();
        }
      });

      if (state.tableData.length === 0) {
        return;
      }

      // Create data copy to avoid reactivity issues
      const data = JSON.parse(JSON.stringify(state.tableData));
      const selectedWikis = [...state.selectedWikis];

      // Get unique dates
      const labels = [...new Set(data.map(d => d.date.substring(0, 4)))].sort();
      const colors = ["#3273dc", "#48c774", "#ffdd57", "#f14668", "#00d1b2", "#ff3860", "#209cee", "#ff6348"];

      enabledSeries.value.forEach((series, index) => {
        const canvasId = `chart-${series.key}`;
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
          return;
        }

        // Make sure the canvas has a valid 2D context
        try {
          const context = ctx.getContext('2d');
          if (!context) {
            return;
          }
        } catch (error) {
          return;
        }

        const datasets = [];
        let colorIndex = 0;

        selectedWikis.forEach(wiki => {
          const seriesData = labels.map(year => {
            // Find all entries for this wiki and year, then take the latest one
            const yearEntries = data.filter(d => d.wiki === wiki && d.date.startsWith(year));
            const latestEntry = yearEntries.sort((a, b) => b.date.localeCompare(a.date))[0];
            return latestEntry ? (latestEntry[series.key] || 0) : null;
          });

          if (seriesData.some(val => val !== null && val !== undefined)) {
            datasets.push({
              label: wiki,
              data: seriesData,
              borderColor: colors[colorIndex % colors.length],
              backgroundColor: colors[colorIndex % colors.length] + "20",
              tension: 0.1,
              pointRadius: 0,
              fill: false,
            });
            colorIndex++;
          }
        });

        try {
          new Chart(ctx, {
            type: "line",
            data: {
              labels: labels,
              datasets: datasets,
            },
            options: {
              responsive: false,
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
        } catch (error) {
          // Chart creation failed, skip silently
          return;
        }
      });
    }

    // Update the single FRS Key chart based on selected metric
    function updateFrsKeyChart() {
      console.log('=== FRS KEY CHART UPDATE DEBUG ===');
      console.log('updateFrsKeyChart called, selectedFrsKey:', state.selectedFrsKey);
      console.log('selectedWikis:', state.selectedWikis);
      console.log('tableData length:', state.tableData.length);

      if (state.tableData.length === 0) {
        console.log('No table data, returning');
        return;
      }

      // Destroy existing single chart if it exists
      if (state.singleChart) {
        state.singleChart.destroy();
        state.singleChart = null;
      }

      const ctx = document.getElementById('singleFrsKeyChart');
      if (!ctx) {
        console.log('singleFrsKeyChart canvas not found');
        return;
      }

      // Get the label for the selected FRS key
      const seriesConfig = {
        pendingLag_average: "Pending Lag (Average)",
        totalPages_ns0: "Total Pages (NS:0)",
        reviewedPages_ns0: "Reviewed Pages (NS:0)",
        syncedPages_ns0: "Synced Pages (NS:0)",
        pendingChanges: "Pending Changes",
        number_of_reviewers: "Number of Reviewers",
        number_of_reviews: "Number of Reviews",
        reviews_per_reviewer: "Reviews Per Reviewer",
      };

      const selectedLabel = seriesConfig[state.selectedFrsKey] || state.selectedFrsKey;

      // Prepare data
      const data = JSON.parse(JSON.stringify(state.tableData));
      const selectedWikis = [...state.selectedWikis];
      const labels = [...new Set(data.map(d => d.date.substring(0, 4)))].sort();
      const colors = ["#3273dc", "#48c774", "#ffdd57", "#f14668", "#00d1b2", "#ff3860", "#209cee", "#ff6348"];

      const datasets = [];
      let colorIndex = 0;

      selectedWikis.forEach(wiki => {
        const seriesData = labels.map(year => {
          // Find all entries for this wiki and year, then take the latest one
          const yearEntries = data.filter(d => d.wiki === wiki && d.date.startsWith(year));
          const latestEntry = yearEntries.sort((a, b) => b.date.localeCompare(a.date))[0];
          return latestEntry ? (latestEntry[state.selectedFrsKey] || null) : null;
        });

        // Debug: Log the data for each wiki
        console.log(`${wiki}wiki_p ${state.selectedFrsKey} data:`, seriesData);
        console.log(`${wiki}wiki_p non-null values:`, seriesData.filter(val => val !== null && val !== undefined));

        if (seriesData.some(val => val !== null && val !== undefined)) {
          datasets.push({
            label: `${wiki}wiki_p`,
            data: seriesData,
            borderColor: colors[colorIndex % colors.length],
            backgroundColor: colors[colorIndex % colors.length] + "20",
            tension: 0.4,
            borderWidth: 3,
            pointRadius: 0,
            fill: false,
          });
          colorIndex++;
        }
      });

      console.log(`Creating FRS Key chart for ${selectedLabel} with ${datasets.length} datasets`);

      // If no datasets available, show a message instead of creating an empty chart
      if (datasets.length === 0) {
        console.log('No datasets available - showing no data message');
        // Clear any existing chart
        if (state.singleChart) {
          state.singleChart.destroy();
          state.singleChart = null;
        }

        // Show a message in the canvas area
        ctx.style.display = 'none';

        // Create a message element if it doesn't exist
        let messageEl = ctx.parentElement.querySelector('.no-data-message');
        if (!messageEl) {
          messageEl = document.createElement('div');
          messageEl.className = 'no-data-message';
          messageEl.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: center;
            height: 300px;
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            color: #6c757d;
            font-size: 16px;
            text-align: center;
            padding: 20px;
          `;
          messageEl.innerHTML = `
            <div>
              <strong>No data available</strong><br>
              The selected wikis (${selectedWikis.map(w => `${w}wiki_p`).join(', ')})
              have no data for "${selectedLabel}".
            </div>
          `;
          ctx.parentElement.appendChild(messageEl);
        }
        messageEl.style.display = 'flex';
        return;
      }

      // Hide any existing no-data message
      const messageEl = ctx.parentElement.querySelector('.no-data-message');
      if (messageEl) {
        messageEl.style.display = 'none';
      }
      ctx.style.display = 'block';

      // Create the chart
      state.singleChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: datasets,
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: {
            duration: 750,
          },
          interaction: {
            mode: 'index',
            intersect: false,
          },
          plugins: {
            title: {
              display: true,
              text: selectedLabel,
              font: {
                size: 16,
                weight: 'bold',
              },
            },
            legend: {
              display: true,
              position: 'right',
              align: 'center',
              labels: {
                boxWidth: 12,
                padding: 10,
                font: {
                  size: 11,
                },
              },
            },
          },
          scales: {
            x: {
              type: 'category',
              grid: {
                display: true,
                color: 'rgba(0, 0, 0, 0.05)',
              },
              ticks: {
                maxRotation: 0,
                minRotation: 0,
                autoSkip: true,
                callback: function(value, index, ticks) {
                  // Extract year from the date string
                  const dateStr = this.getLabelForValue(value);
                  if (dateStr) {
                    const year = dateStr.split('-')[0];
                    // Only show year for the first occurrence of each year
                    if (index === 0) {
                      return year;
                    }
                    // Check if this year is different from the previous tick's year
                    const prevDateStr = this.getLabelForValue(ticks[index - 1].value);
                    const prevYear = prevDateStr ? prevDateStr.split('-')[0] : '';
                    if (year !== prevYear) {
                      return year;
                    }
                    return '';
                  }
                  return '';
                },
              },
            },
            y: {
              beginAtZero: true,
              grid: {
                display: true,
                color: 'rgba(0, 0, 0, 0.05)',
              },
              ticks: {
                callback: function(value) {
                  return value.toLocaleString();
                },
              },
            },
          },
        },
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
        if (state.selectedMonth && state.filterMode === 'yearmonth') {
          // Only apply month filtering when in YearMonth mode
          // Convert month selection (e.g., "202412") to date range
          const year = parseInt(state.selectedMonth.substring(0, 4));
          const month = parseInt(state.selectedMonth.substring(4, 6));
          const startDate = `${year}-${String(month).padStart(2, '0')}-01`;
          // Get last day of the month
          const lastDay = new Date(year, month, 0).getDate();
          const endDate = `${year}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
          apiParams.set('start_date', startDate);
          apiParams.set('end_date', endDate);
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

        state.tableData = allData;
        state.lastUpdated = new Date();


        // Update available months based on loaded data (only if not already loaded from API)
        if (state.availableMonths.length === 0) {
          updateAvailableMonthsFromData(allData);
        }

        // Update chart after a small delay to avoid reactivity issues
        setTimeout(async () => {
          if (state.filterMode === 'wiki') {
            // Wait for Vue to update the DOM with new canvas elements
            await nextTick();
            setTimeout(() => {
              updateChart();
            }, 200);
          } else if (state.filterMode === 'frs_key') {
            // For FRS Key mode, call updateFrsKeyChart
            await nextTick();
            updateFrsKeyChart();
          } else {
            updateChart();
          }
        }, 100);

      } catch (error) {
        state.error = error.message;
      } finally {
        // Update timestamp when data loading completes (success or failure)
        state.lastUpdated = new Date().toISOString();
        state.loading = false;
      }
    }

    async function refreshData() {
      await loadData();
    }

    // URL management
    function updateUrl() {
      const params = new URLSearchParams();

      // Handle filter mode
      if (state.filterMode && state.filterMode !== 'wiki') {
        params.set('mode', state.filterMode);
      }

      // Handle wiki selection
      if (state.selectedWikis.length === 1) {
        // Single wiki - use 'wiki' parameter with wiki_p format
        params.set('wiki', `${state.selectedWikis[0]}wiki_p`);
      } else if (state.selectedWikis.length > 1) {
        // Multiple wikis - use 'db' parameter with wiki_p format
        const wikisWithSuffix = state.selectedWikis.map(w => `${w}wiki_p`);
        params.set('db', wikisWithSuffix.join(','));
      }

      // Handle FRS key selection (only in frs_key mode)
      if (state.filterMode === 'frs_key' && state.selectedFrsKey) {
        // Convert underscore to hyphen for URL (e.g., pendingLag_average -> pendingLag-average)
        const frsKeyParam = state.selectedFrsKey.replace(/_/g, '-');
        params.set('frs_key', frsKeyParam);
      }

      // Handle month selection (only in yearmonth mode)
      if (state.filterMode === 'yearmonth' && state.selectedMonth) {
        // Convert YYYYMM to YYYY-MM format
        const year = state.selectedMonth.substring(0, 4);
        const month = state.selectedMonth.substring(4, 6);
        params.set('month', `${year}-${month}`);
      }

      const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
      window.history.replaceState({}, '', newUrl);
    }

    // Load URL parameters on mount
    function loadUrlParams() {
      const params = new URLSearchParams(window.location.search);

      // Handle 'mode' parameter (filter mode)
      const modeParam = params.get('mode');
      if (modeParam && ['wiki', 'frs_key', 'yearmonth'].includes(modeParam)) {
        state.filterMode = modeParam;
      }

      // Handle 'db' parameter (multiple wikis) - format: fiwiki_p,dewiki_p
      const dbParam = params.get('db');
      if (dbParam) {
        state.selectedWikis = dbParam.split(',').map(w => {
          // Remove wiki_p suffix if present
          return w.endsWith('wiki_p') ? w.slice(0, -6) : w;
        }).filter(w =>
          AVAILABLE_WIKIS.some(aw => aw.code === w)
        );
      }

      // Handle 'wiki' parameter (single wiki - overrides 'db') - format: fiwiki_p
      const wikiParam = params.get('wiki');
      if (wikiParam) {
        // Remove wiki_p suffix if present
        const wikiCode = wikiParam.endsWith('wiki_p') ? wikiParam.slice(0, -6) : wikiParam;
        const wiki = AVAILABLE_WIKIS.find(aw => aw.code === wikiCode);
        if (wiki) {
          state.selectedWikis = [wikiCode];
        }
      }

      // Handle 'frs_key' parameter in frs_key mode - format: pendingLag-average
      const frsKeyParam = params.get('frs_key');
      if (frsKeyParam && state.filterMode === 'frs_key') {
        // Convert hyphen to underscore (e.g., pendingLag-average -> pendingLag_average)
        const frsKey = frsKeyParam.replace(/-/g, '_');
        if (state.series.hasOwnProperty(frsKey)) {
          state.selectedFrsKey = frsKey;
        }
      }

      // Handle 'month' parameter (single month view) - format: 2024-01
      const monthParam = params.get('month');
      if (monthParam && state.filterMode === 'yearmonth') {
        // Convert YYYY-MM to YYYYMM format
        state.selectedMonth = monthParam.replace('-', '');
      }
    }

    // Watchers
    watch(() => state.selectedWikis, async () => {
      console.log('=== SELECTED WIKIS WATCHER DEBUG ===');
      console.log('selectedWikis changed:', state.selectedWikis);
      console.log('selectedWikis length:', state.selectedWikis.length);
      console.log('filterMode:', state.filterMode);
      updateUrl();

      // Call the appropriate chart update function based on filter mode
      if (state.filterMode === 'frs_key') {
        // Add a small delay to ensure DOM updates are complete
        await nextTick();
        setTimeout(() => {
          updateFrsKeyChart();
        }, 50);
      } else {
        loadData();
      }
    }, { deep: true });

    watch(() => state.selectedMonth, () => {
      updateUrl();
      // Add a small delay to ensure DOM is ready
      setTimeout(() => {
        loadData();
      }, 100);
    });

    // Removed series watcher

    watch(() => state.filterMode, async () => {
      updateUrl();

      // Clear selectedMonth when switching away from YearMonth mode
      if (state.filterMode !== 'yearmonth' && state.selectedMonth) {
        state.selectedMonth = '';
      }

      // Initialize selectedWikis based on filter mode
      if (state.filterMode === 'frs_key') {
        // In FRS Key mode, select all available wikis by default
        if (state.selectedWikis.length === 0) {
          state.selectedWikis = AVAILABLE_WIKIS.map(w => w.code);
        }
      } else if (state.filterMode === 'wiki') {
        // In Wiki mode, initialize selectedWikiForTable if not set
        if (!state.selectedWikiForTable) {
          state.selectedWikiForTable = AVAILABLE_WIKIS[0].code;
        }
      }

      // Trigger appropriate chart rendering when filter mode changes
      if (state.filterMode === 'wiki') {
        // Wait for Vue to update the DOM with new canvas elements
        await nextTick();
        setTimeout(() => {
          updateChart();
        }, 500);  // Increased timeout to give Vue more time to render
      } else if (state.filterMode === 'frs_key') {
        await nextTick();
        updateFrsKeyChart();
      } else {
        updateChart();
      }
    });

    // Watch for changes to selectedFrsKey and update the chart
    watch(() => state.selectedFrsKey, async () => {
      if (state.filterMode === 'frs_key') {
        updateUrl();
        await nextTick();
        updateFrsKeyChart();
      }
    });

    // Extract unique months from loaded data
    function updateAvailableMonthsFromData(data) {
      const uniqueDates = [...new Set(data.map(d => d.date))];
      const months = uniqueDates
        .map(date => {
          const dateObj = new Date(date);
          const monthValue = dateObj.getFullYear().toString() +
                           String(dateObj.getMonth() + 1).padStart(2, '0');
          return { value: monthValue, label: monthValue };
        })
        .sort((a, b) => b.value.localeCompare(a.value)); // Sort newest first

      // Only update if we have new months
      if (months.length > 0) {
        state.availableMonths = months;
      }
    }

    // Load available months from database
    async function loadAvailableMonths() {
      try {
        const response = await fetch('/api/statistics/available-months/');
        const data = await response.json();
        state.availableMonths = data.months || [];
      } catch (error) {
        console.error('Error loading available months:', error);
        // If API fails, leave empty array - months will be populated when data loads
        state.availableMonths = [];
      }
    }

    // Lifecycle
    onMounted(async () => {
      await loadAvailableMonths();
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
      availableMonths: computed(() => state.availableMonths),
      enabledSeries,
      isSingleMonthView,
      singleMonthData,
      yearMonthTableData,
      yearMonthTableTitle,
      selectedFrsKeyLabel,
      frsKeyTableDates,
      wikiTableData,
      lastUpdatedFormatted,
      getFrsKeyValue,
      filteredTableData,
      loadData,
      refreshData,
      updateUrl,
    };
  }
}).mount('#app');
