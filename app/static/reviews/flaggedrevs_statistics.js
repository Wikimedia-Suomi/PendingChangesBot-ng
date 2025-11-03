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
      isUpdatingChart: false, // Flag to prevent concurrent chart updates

      // Chart
      chart: null,
      singleChart: null, // For FRS Key mode single chart

      // Filters
      selectedWikis: [],
      filterMode: 'wiki', // 'wiki', 'frs_key', 'single_wiki', 'yearmonth'
      selectedFrsKey: 'pendingLag_average', // Default FRS key selection
      selectedWikiForTable: 'fi', // Default wiki for table display
      selectedSingleWiki: 'fi', // Selected wiki for single wiki mode
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
      focusedWiki: null,
      filteredDate: null, // For filtering table by specific date
      filteredWikiDate: null, // For filtering Wiki table by specific date

      // YearMonth view controls
      showGraph: true, // Show chart in YearMonth mode
      showTable: true, // Show table in YearMonth mode
      yearMonthChart: null, // Chart instance for YearMonth mode

      // Time period selection (default = full data)
      timePeriod: 'all', // 'all', 'custom', 'last_year', 'last_6_months', 'last_3_months', 'last_month', 'select_year'
      startDate: null, // Custom start date (YYYY-MM-DD format)
      endDate: null, // Custom end date (YYYY-MM-DD format)
      selectedYear: null, // Selected year for 'select_year' time period

      // Data resolution selection
      dataResolution: 'yearly', // 'yearly', 'monthly', 'daily'
    });

    // Initialize with default wiki if none selected
    if (state.selectedWikis.length === 0 && AVAILABLE_WIKIS.length > 0) {
      const defaultWiki = AVAILABLE_WIKIS.find(w => w.code === 'fi') || AVAILABLE_WIKIS[0];
      state.selectedWikis = [defaultWiki.code];
    }

    // Function to generate a distinct color for a wiki code
    // Uses a hash function to generate consistent colors for each wiki
    const getWikiColor = (wikiCode) => {
      // Predefined colors for better visual distinction
      const predefinedColors = [
        '#3273dc', '#48c774', '#ffdd57', '#f14668', '#00d1b2',
        '#ff3860', '#209cee', '#ff6348', '#9b59b6', '#e74c3c',
        '#3498db', '#2ecc71', '#f39c12', '#e67e22', '#1abc9c',
        '#34495e', '#16a085', '#27ae60', '#2980b9', '#8e44ad',
        '#c0392b', '#d35400', '#f1c40f', '#2ecc71', '#3498db'
      ];

      // Predefined mapping for common wikis (keep these recognizable)
      const wikiColorMap = {
        'de': '#FF0000',  // Red
        'en': '#00FF00',  // Green
        'fi': '#0000FF',  // Blue
        'pl': '#FF00FF',  // Magenta
        'ru': '#FFFF00',  // Yellow
        'fr': '#FFA500',  // Orange
        'es': '#800080',  // Purple
        'it': '#00FFFF',  // Cyan
        'pt': '#FF1493',  // Deep Pink
        'ja': '#FFD700',  // Gold
        'zh': '#FF4500',  // Orange Red
        'ar': '#32CD32',  // Lime Green
        'nl': '#9370DB',  // Medium Purple
        'sv': '#00CED1',  // Dark Turquoise
        'no': '#FF69B4',  // Hot Pink
      };

      // Return predefined color if available
      if (wikiColorMap[wikiCode]) {
        return wikiColorMap[wikiCode];
      }

      // Generate color using hash function for consistent colors
      let hash = 0;
      for (let i = 0; i < wikiCode.length; i++) {
        hash = wikiCode.charCodeAt(i) + ((hash << 5) - hash);
      }

      // Use hash to pick from predefined colors
      const colorIndex = Math.abs(hash) % predefinedColors.length;
      return predefinedColors[colorIndex];
    };

    // Computed properties
    const availableWikis = computed(() => AVAILABLE_WIKIS);

    const availableYears = computed(() => {
      const currentYear = new Date().getFullYear();
      const years = [];
      for (let year = 2010; year <= currentYear; year++) {
        years.push(year);
      }
      return years.reverse(); // Most recent year first
    });

    const filteredTableData = computed(() => {
      let filtered = state.tableData.filter(entry => {
        if (state.selectedWikis.length > 0 && !state.selectedWikis.includes(entry.wiki)) {
          return false;
        }
        return true;
      });

      // Aggregate data based on resolution
      if (state.dataResolution === 'yearly') {
        // Group by year and wiki, calculate averages
        const groupedByYear = {};
        filtered.forEach(entry => {
          const year = entry.date.substring(0, 4);
          const key = `${entry.wiki}_${year}`;
          if (!groupedByYear[key]) {
            groupedByYear[key] = {
              wiki: entry.wiki,
              date: year + '-01-01',
              pendingLag_average: [],
              totalPages_ns0: [],
              reviewedPages_ns0: [],
              syncedPages_ns0: [],
              pendingChanges: [],
              number_of_reviewers: [],
              number_of_reviews: [],
              reviews_per_reviewer: []
            };
          }
          if (entry.pendingLag_average !== null && entry.pendingLag_average !== undefined) {
            groupedByYear[key].pendingLag_average.push(entry.pendingLag_average);
          }
          if (entry.totalPages_ns0 !== null && entry.totalPages_ns0 !== undefined) {
            groupedByYear[key].totalPages_ns0.push(entry.totalPages_ns0);
          }
          if (entry.reviewedPages_ns0 !== null && entry.reviewedPages_ns0 !== undefined) {
            groupedByYear[key].reviewedPages_ns0.push(entry.reviewedPages_ns0);
          }
          if (entry.syncedPages_ns0 !== null && entry.syncedPages_ns0 !== undefined) {
            groupedByYear[key].syncedPages_ns0.push(entry.syncedPages_ns0);
          }
          if (entry.pendingChanges !== null && entry.pendingChanges !== undefined) {
            groupedByYear[key].pendingChanges.push(entry.pendingChanges);
          }
          if (entry.number_of_reviewers !== null && entry.number_of_reviewers !== undefined) {
            groupedByYear[key].number_of_reviewers.push(entry.number_of_reviewers);
          }
          if (entry.number_of_reviews !== null && entry.number_of_reviews !== undefined) {
            groupedByYear[key].number_of_reviews.push(entry.number_of_reviews);
          }
          if (entry.reviews_per_reviewer !== null && entry.reviews_per_reviewer !== undefined) {
            groupedByYear[key].reviews_per_reviewer.push(entry.reviews_per_reviewer);
          }
        });

        // Calculate averages
        return Object.values(groupedByYear).map(yearData => ({
          ...yearData,
          pendingLag_average: yearData.pendingLag_average.length > 0
            ? yearData.pendingLag_average.reduce((a, b) => a + b, 0) / yearData.pendingLag_average.length
            : null,
          totalPages_ns0: yearData.totalPages_ns0.length > 0
            ? Math.round(yearData.totalPages_ns0.reduce((a, b) => a + b, 0) / yearData.totalPages_ns0.length)
            : null,
          reviewedPages_ns0: yearData.reviewedPages_ns0.length > 0
            ? Math.round(yearData.reviewedPages_ns0.reduce((a, b) => a + b, 0) / yearData.reviewedPages_ns0.length)
            : null,
          syncedPages_ns0: yearData.syncedPages_ns0.length > 0
            ? Math.round(yearData.syncedPages_ns0.reduce((a, b) => a + b, 0) / yearData.syncedPages_ns0.length)
            : null,
          pendingChanges: yearData.pendingChanges.length > 0
            ? Math.round(yearData.pendingChanges.reduce((a, b) => a + b, 0) / yearData.pendingChanges.length)
            : null,
          number_of_reviewers: yearData.number_of_reviewers.length > 0
            ? Math.round(yearData.number_of_reviewers.reduce((a, b) => a + b, 0) / yearData.number_of_reviewers.length)
            : null,
          number_of_reviews: yearData.number_of_reviews.length > 0
            ? Math.round(yearData.number_of_reviews.reduce((a, b) => a + b, 0) / yearData.number_of_reviews.length)
            : null,
          reviews_per_reviewer: yearData.reviews_per_reviewer.length > 0
            ? yearData.reviews_per_reviewer.reduce((a, b) => a + b, 0) / yearData.reviews_per_reviewer.length
            : null
        })).sort((a, b) => {
          const dateCompare = a.date.localeCompare(b.date);
          return dateCompare !== 0 ? dateCompare : a.wiki.localeCompare(b.wiki);
        });
      } else if (state.dataResolution === 'monthly') {
        // Group by year-month and wiki, calculate averages
        const groupedByMonth = {};
        filtered.forEach(entry => {
          const yearMonth = entry.date.substring(0, 7); // YYYY-MM
          const key = `${entry.wiki}_${yearMonth}`;
          if (!groupedByMonth[key]) {
            groupedByMonth[key] = {
              wiki: entry.wiki,
              date: yearMonth + '-01',
              pendingLag_average: [],
              totalPages_ns0: [],
              reviewedPages_ns0: [],
              syncedPages_ns0: [],
              pendingChanges: [],
              number_of_reviewers: [],
              number_of_reviews: [],
              reviews_per_reviewer: []
            };
          }
          if (entry.pendingLag_average !== null && entry.pendingLag_average !== undefined) {
            groupedByMonth[key].pendingLag_average.push(entry.pendingLag_average);
          }
          if (entry.totalPages_ns0 !== null && entry.totalPages_ns0 !== undefined) {
            groupedByMonth[key].totalPages_ns0.push(entry.totalPages_ns0);
          }
          if (entry.reviewedPages_ns0 !== null && entry.reviewedPages_ns0 !== undefined) {
            groupedByMonth[key].reviewedPages_ns0.push(entry.reviewedPages_ns0);
          }
          if (entry.syncedPages_ns0 !== null && entry.syncedPages_ns0 !== undefined) {
            groupedByMonth[key].syncedPages_ns0.push(entry.syncedPages_ns0);
          }
          if (entry.pendingChanges !== null && entry.pendingChanges !== undefined) {
            groupedByMonth[key].pendingChanges.push(entry.pendingChanges);
          }
          if (entry.number_of_reviewers !== null && entry.number_of_reviewers !== undefined) {
            groupedByMonth[key].number_of_reviewers.push(entry.number_of_reviewers);
          }
          if (entry.number_of_reviews !== null && entry.number_of_reviews !== undefined) {
            groupedByMonth[key].number_of_reviews.push(entry.number_of_reviews);
          }
          if (entry.reviews_per_reviewer !== null && entry.reviews_per_reviewer !== undefined) {
            groupedByMonth[key].reviews_per_reviewer.push(entry.reviews_per_reviewer);
          }
        });

        // Calculate averages
        return Object.values(groupedByMonth).map(monthData => ({
          ...monthData,
          pendingLag_average: monthData.pendingLag_average.length > 0
            ? monthData.pendingLag_average.reduce((a, b) => a + b, 0) / monthData.pendingLag_average.length
            : null,
          totalPages_ns0: monthData.totalPages_ns0.length > 0
            ? Math.round(monthData.totalPages_ns0.reduce((a, b) => a + b, 0) / monthData.totalPages_ns0.length)
            : null,
          reviewedPages_ns0: monthData.reviewedPages_ns0.length > 0
            ? Math.round(monthData.reviewedPages_ns0.reduce((a, b) => a + b, 0) / monthData.reviewedPages_ns0.length)
            : null,
          syncedPages_ns0: monthData.syncedPages_ns0.length > 0
            ? Math.round(monthData.syncedPages_ns0.reduce((a, b) => a + b, 0) / monthData.syncedPages_ns0.length)
            : null,
          pendingChanges: monthData.pendingChanges.length > 0
            ? Math.round(monthData.pendingChanges.reduce((a, b) => a + b, 0) / monthData.pendingChanges.length)
            : null,
          number_of_reviewers: monthData.number_of_reviewers.length > 0
            ? Math.round(monthData.number_of_reviewers.reduce((a, b) => a + b, 0) / monthData.number_of_reviewers.length)
            : null,
          number_of_reviews: monthData.number_of_reviews.length > 0
            ? Math.round(monthData.number_of_reviews.reduce((a, b) => a + b, 0) / monthData.number_of_reviews.length)
            : null,
          reviews_per_reviewer: monthData.reviews_per_reviewer.length > 0
            ? monthData.reviews_per_reviewer.reduce((a, b) => a + b, 0) / monthData.reviews_per_reviewer.length
            : null
        })).sort((a, b) => {
          const dateCompare = a.date.localeCompare(b.date);
          return dateCompare !== 0 ? dateCompare : a.wiki.localeCompare(b.wiki);
        });
      }

      // For daily resolution, return as-is
      return filtered;
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

      // Filter by state.series to show/hide graphs based on toggles
      return seriesConfig.filter(series => state.series[series.key]);
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

      // Get unique dates based on resolution
      let dateGroups = [];

      if (state.dataResolution === 'yearly') {
        // Group by year
        const years = [...new Set(state.tableData.map(d => d.date.substring(0, 4)))].sort();
        dateGroups = years.map(year => ({ group: year, date: year + '-01-01' }));
      } else if (state.dataResolution === 'monthly') {
        // Group by year-month
        const yearMonths = [...new Set(state.tableData.map(d => d.date.substring(0, 7)))].sort();
        dateGroups = yearMonths.map(ym => ({ group: ym, date: ym + '-01' }));
      } else {
        // Daily - use full dates
        const dates = [...new Set(state.tableData.map(d => d.date))].sort();
        dateGroups = dates.map(date => ({ group: date, date: date }));
      }

      // If a specific date is filtered, show only matching group
      if (state.filteredDate) {
        if (state.dataResolution === 'yearly') {
          const filteredYear = state.filteredDate.substring(0, 4);
          dateGroups = dateGroups.filter(d => d.group === filteredYear);
        } else if (state.dataResolution === 'monthly') {
          const filteredYearMonth = state.filteredDate.substring(0, 7);
          dateGroups = dateGroups.filter(d => d.group === filteredYearMonth);
        } else {
          dateGroups = dateGroups.filter(d => d.group === state.filteredDate);
        }
      }

      // Format for display
      return dateGroups.map(d => {
        if (state.dataResolution === 'yearly') {
          return d.group; // Just the year
        } else if (state.dataResolution === 'monthly') {
          return d.group.replace('-', ''); // YYYYMM
        } else {
          return d.date.replace('-', '').substring(0, 6); // YYYYMM
        }
      });
    });

    // Wiki table data for the selected wiki only
    const wikiTableData = computed(() => {
      if (state.filterMode !== 'wiki' || !state.tableData.length) return [];

      // Filter data for the selected wiki only
      let filteredData = state.tableData
        .filter(entry => entry.wiki === state.selectedWikiForTable)
        .sort((a, b) => a.date.localeCompare(b.date));

      // If a specific date is filtered, show only that date
      if (state.filteredWikiDate) {
        filteredData = filteredData.filter(entry => entry.date === state.filteredWikiDate);
        return filteredData;
      }

      // Aggregate data based on resolution
      if (state.dataResolution === 'yearly') {
        // Group by year and calculate averages
        const groupedByYear = {};
        filteredData.forEach(entry => {
          const year = entry.date.substring(0, 4);
          if (!groupedByYear[year]) {
            groupedByYear[year] = {
              wiki: entry.wiki,
              date: year + '-01-01', // Use first day of year for date
              pendingLag_average: [],
              totalPages_ns0: [],
              reviewedPages_ns0: [],
              syncedPages_ns0: [],
              pendingChanges: [],
              number_of_reviewers: [],
              number_of_reviews: [],
              reviews_per_reviewer: []
            };
          }
          if (entry.pendingLag_average !== null && entry.pendingLag_average !== undefined) {
            groupedByYear[year].pendingLag_average.push(entry.pendingLag_average);
          }
          if (entry.totalPages_ns0 !== null && entry.totalPages_ns0 !== undefined) {
            groupedByYear[year].totalPages_ns0.push(entry.totalPages_ns0);
          }
          if (entry.reviewedPages_ns0 !== null && entry.reviewedPages_ns0 !== undefined) {
            groupedByYear[year].reviewedPages_ns0.push(entry.reviewedPages_ns0);
          }
          if (entry.syncedPages_ns0 !== null && entry.syncedPages_ns0 !== undefined) {
            groupedByYear[year].syncedPages_ns0.push(entry.syncedPages_ns0);
          }
          if (entry.pendingChanges !== null && entry.pendingChanges !== undefined) {
            groupedByYear[year].pendingChanges.push(entry.pendingChanges);
          }
          if (entry.number_of_reviewers !== null && entry.number_of_reviewers !== undefined) {
            groupedByYear[year].number_of_reviewers.push(entry.number_of_reviewers);
          }
          if (entry.number_of_reviews !== null && entry.number_of_reviews !== undefined) {
            groupedByYear[year].number_of_reviews.push(entry.number_of_reviews);
          }
          if (entry.reviews_per_reviewer !== null && entry.reviews_per_reviewer !== undefined) {
            groupedByYear[year].reviews_per_reviewer.push(entry.reviews_per_reviewer);
          }
        });

        // Calculate averages
        return Object.values(groupedByYear).map(yearData => ({
          ...yearData,
          pendingLag_average: yearData.pendingLag_average.length > 0
            ? yearData.pendingLag_average.reduce((a, b) => a + b, 0) / yearData.pendingLag_average.length
            : null,
          totalPages_ns0: yearData.totalPages_ns0.length > 0
            ? Math.round(yearData.totalPages_ns0.reduce((a, b) => a + b, 0) / yearData.totalPages_ns0.length)
            : null,
          reviewedPages_ns0: yearData.reviewedPages_ns0.length > 0
            ? Math.round(yearData.reviewedPages_ns0.reduce((a, b) => a + b, 0) / yearData.reviewedPages_ns0.length)
            : null,
          syncedPages_ns0: yearData.syncedPages_ns0.length > 0
            ? Math.round(yearData.syncedPages_ns0.reduce((a, b) => a + b, 0) / yearData.syncedPages_ns0.length)
            : null,
          pendingChanges: yearData.pendingChanges.length > 0
            ? Math.round(yearData.pendingChanges.reduce((a, b) => a + b, 0) / yearData.pendingChanges.length)
            : null,
          number_of_reviewers: yearData.number_of_reviewers.length > 0
            ? Math.round(yearData.number_of_reviewers.reduce((a, b) => a + b, 0) / yearData.number_of_reviewers.length)
            : null,
          number_of_reviews: yearData.number_of_reviews.length > 0
            ? Math.round(yearData.number_of_reviews.reduce((a, b) => a + b, 0) / yearData.number_of_reviews.length)
            : null,
          reviews_per_reviewer: yearData.reviews_per_reviewer.length > 0
            ? yearData.reviews_per_reviewer.reduce((a, b) => a + b, 0) / yearData.reviews_per_reviewer.length
            : null
        })).sort((a, b) => a.date.localeCompare(b.date));
      } else if (state.dataResolution === 'monthly') {
        // Group by year-month and calculate averages
        const groupedByMonth = {};
        filteredData.forEach(entry => {
          const yearMonth = entry.date.substring(0, 7); // YYYY-MM
          if (!groupedByMonth[yearMonth]) {
            groupedByMonth[yearMonth] = {
              wiki: entry.wiki,
              date: yearMonth + '-01', // Use first day of month for date
              pendingLag_average: [],
              totalPages_ns0: [],
              reviewedPages_ns0: [],
              syncedPages_ns0: [],
              pendingChanges: [],
              number_of_reviewers: [],
              number_of_reviews: [],
              reviews_per_reviewer: []
            };
          }
          if (entry.pendingLag_average !== null && entry.pendingLag_average !== undefined) {
            groupedByMonth[yearMonth].pendingLag_average.push(entry.pendingLag_average);
          }
          if (entry.totalPages_ns0 !== null && entry.totalPages_ns0 !== undefined) {
            groupedByMonth[yearMonth].totalPages_ns0.push(entry.totalPages_ns0);
          }
          if (entry.reviewedPages_ns0 !== null && entry.reviewedPages_ns0 !== undefined) {
            groupedByMonth[yearMonth].reviewedPages_ns0.push(entry.reviewedPages_ns0);
          }
          if (entry.syncedPages_ns0 !== null && entry.syncedPages_ns0 !== undefined) {
            groupedByMonth[yearMonth].syncedPages_ns0.push(entry.syncedPages_ns0);
          }
          if (entry.pendingChanges !== null && entry.pendingChanges !== undefined) {
            groupedByMonth[yearMonth].pendingChanges.push(entry.pendingChanges);
          }
          if (entry.number_of_reviewers !== null && entry.number_of_reviewers !== undefined) {
            groupedByMonth[yearMonth].number_of_reviewers.push(entry.number_of_reviewers);
          }
          if (entry.number_of_reviews !== null && entry.number_of_reviews !== undefined) {
            groupedByMonth[yearMonth].number_of_reviews.push(entry.number_of_reviews);
          }
          if (entry.reviews_per_reviewer !== null && entry.reviews_per_reviewer !== undefined) {
            groupedByMonth[yearMonth].reviews_per_reviewer.push(entry.reviews_per_reviewer);
          }
        });

        // Calculate averages
        return Object.values(groupedByMonth).map(monthData => ({
          ...monthData,
          pendingLag_average: monthData.pendingLag_average.length > 0
            ? monthData.pendingLag_average.reduce((a, b) => a + b, 0) / monthData.pendingLag_average.length
            : null,
          totalPages_ns0: monthData.totalPages_ns0.length > 0
            ? Math.round(monthData.totalPages_ns0.reduce((a, b) => a + b, 0) / monthData.totalPages_ns0.length)
            : null,
          reviewedPages_ns0: monthData.reviewedPages_ns0.length > 0
            ? Math.round(monthData.reviewedPages_ns0.reduce((a, b) => a + b, 0) / monthData.reviewedPages_ns0.length)
            : null,
          syncedPages_ns0: monthData.syncedPages_ns0.length > 0
            ? Math.round(monthData.syncedPages_ns0.reduce((a, b) => a + b, 0) / monthData.syncedPages_ns0.length)
            : null,
          pendingChanges: monthData.pendingChanges.length > 0
            ? Math.round(monthData.pendingChanges.reduce((a, b) => a + b, 0) / monthData.pendingChanges.length)
            : null,
          number_of_reviewers: monthData.number_of_reviewers.length > 0
            ? Math.round(monthData.number_of_reviewers.reduce((a, b) => a + b, 0) / monthData.number_of_reviewers.length)
            : null,
          number_of_reviews: monthData.number_of_reviews.length > 0
            ? Math.round(monthData.number_of_reviews.reduce((a, b) => a + b, 0) / monthData.number_of_reviews.length)
            : null,
          reviews_per_reviewer: monthData.reviews_per_reviewer.length > 0
            ? monthData.reviews_per_reviewer.reduce((a, b) => a + b, 0) / monthData.reviews_per_reviewer.length
            : null
        })).sort((a, b) => a.date.localeCompare(b.date));
      }

      // For daily resolution, return as-is
      return filteredData;
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

    // Method to get FRS Key value for a specific wiki and date (aggregated based on resolution)
    function getFrsKeyValue(wiki, date) {
      let matchingEntries = [];

      if (state.dataResolution === 'yearly') {
        // Date is just the year (YYYY)
        const year = date;
        matchingEntries = state.tableData.filter(d =>
          d.wiki === wiki && d.date.startsWith(year)
        );
      } else if (state.dataResolution === 'monthly') {
        // Date is YYYYMM, convert to YYYY-MM
        const year = date.substring(0, 4);
        const month = date.substring(4, 6);
        const yearMonth = `${year}-${month}`;
        matchingEntries = state.tableData.filter(d =>
          d.wiki === wiki && d.date.startsWith(yearMonth)
        );
      } else {
        // Daily - date is YYYYMM, convert to YYYY-MM-DD format for lookup
        const year = date.substring(0, 4);
        const month = date.substring(4, 6);
        const lookupDate = `${year}-${month}-01`;
        matchingEntries = state.tableData.filter(d =>
          d.wiki === wiki && d.date === lookupDate
        );
      }

      if (matchingEntries.length === 0) return 'N/A';

      // Aggregate values based on resolution
      const values = matchingEntries
        .map(entry => entry[state.selectedFrsKey])
        .filter(v => v !== null && v !== undefined);

      if (values.length === 0) return 'N/A';

      // Calculate average
      const average = values.reduce((a, b) => a + b, 0) / values.length;

      // Format based on data type
      if (state.selectedFrsKey === 'pendingLag_average' || state.selectedFrsKey === 'reviews_per_reviewer') {
        return average.toFixed(1);
      } else if (state.selectedFrsKey.includes('Pages') || state.selectedFrsKey === 'pendingChanges') {
        return Math.round(average).toLocaleString();
      } else {
        return Math.round(average).toString();
      }
    }

    // Method to get single date value for YearMonth-style table
    function getSingleDateValue(wiki, field) {
      if (!state.filteredDate) return null;

      const entry = state.tableData.find(d => d.wiki === wiki && d.date === state.filteredDate);
      if (!entry) return null;

      return entry[field];
    }

    // Formatted filtered date for display
    const filteredDateFormatted = computed(() => {
      if (!state.filteredDate) return '';

      // Convert 2023-10-01 to 2023-10 format
      return state.filteredDate.substring(0, 7);
    });

    // Go to wiki page with specific wiki selected
    function goToWikiPage(wiki) {
      console.log('Going to wiki page for:', wiki);
      // Navigate to the wiki page with the specific wiki selected
      // Include current chart selections in URL to preserve them
      const currentWikis = state.selectedWikis.map(w => `${w}wiki_p`).join(',');
      window.location.href = `/flaggedrevs-statistics/?mode=wiki&wiki=${wiki}&db=${currentWikis}`;
    }

    // Filter table to show data for specific date clicked
    function goToDatePage(date) {
      console.log('Filtering table for date:', date);
      // Convert YYYYMM to YYYY-MM-DD format for filtering
      const year = date.substring(0, 4);
      const month = date.substring(4, 6);
      const dateParam = `${year}-${month}-01`;

      // Filter the table data to show only this specific date
      state.filteredDate = dateParam;

      // Update URL to reflect the filtered date
      updateUrl();
    }

    // Go to FRS Key with specific metric selected
    function goToFrsKey(key) {
      console.log('Switching to FRS Key:', key);

      // Switch to FRS Key mode
      state.filterMode = 'frs_key';

      // Clear the filtered date to go back to normal table view
      state.filteredDate = null;

      // Set the selected FRS Key (this will trigger the watcher)
      state.selectedFrsKey = key;

      // Update URL to reflect the changes
      updateUrl();
    }

    // Get data for a specific wiki and date
    function getWikiDateData(wikiCode, date, metric) {
      if (!state.tableData || !date) return null;

      // Find the data entry for this wiki and date
      const entry = state.tableData.find(d => d.wiki === wikiCode && d.date === date);
      return entry ? entry[metric] : null;
    }

    // Go to Wiki mode showing data for specific wiki from date view
    function goToWikiFromDateView(wikiCode) {
      // Clear the filtered date to go back to normal Wiki table view
      state.filteredWikiDate = null;

      // Set the selected wiki for the table
      state.selectedWikiForTable = wikiCode;

      // Update URL to reflect the changes
      updateUrl();
    }

    // Go to YearMonth metric (switches to FRS Key mode like goToFrsKey)
    function goToYearMonthMetric(metric) {
      console.log('Switching to FRS Key from YearMonth:', metric);

      // Switch to FRS Key mode
      state.filterMode = 'frs_key';

      // Set the selected FRS Key (this will trigger the watcher)
      state.selectedFrsKey = metric;

      // Update URL to reflect the changes
      updateUrl();
    }

    // Go to YearMonth wiki (redirects to Wiki page like goToWikiPage)
    function goToYearMonthWiki(wiki) {
      console.log('Going to wiki page from YearMonth for:', wiki);
      // Navigate to the wiki page with the specific wiki selected
      // Include current chart selections in URL to preserve them
      const currentWikis = state.selectedWikis.map(w => `${w}wiki_p`).join(',');
      window.location.href = `/flaggedrevs-statistics/?mode=wiki&wiki=${wiki}&db=${currentWikis}`;
    }

    // YearMonth now reuses the FRS Key chart - no separate chart needed
    function updateYearMonthChart() {
      console.log('=== YEARMONTH CHART UPDATE DEBUG ===');
      console.log('updateYearMonthChart called, selectedFrsKey:', state.selectedFrsKey);
      console.log('selectedWikis:', state.selectedWikis);
      console.log('NOTE: Chart uses ALL data (not filtered by month), only table is filtered by month');

      if (!state.tableData || state.tableData.length === 0) {
        console.log('No table data, returning');
        return;
      }

      // Destroy existing chart if it exists
      if (state.yearMonthChart) {
        try {
          console.log('Destroying existing YearMonth chart...');
          state.yearMonthChart.destroy();
          console.log('YearMonth chart destroyed successfully');
        } catch (error) {
          console.log('Error destroying YearMonth chart:', error);
        }
        state.yearMonthChart = null;
      }

      // Also destroy any chart that Chart.js might have registered for this canvas
      try {
        const canvas = document.getElementById('yearMonthChart');
        if (canvas) {
          const existingChart = Chart.getChart(canvas);
          if (existingChart) {
            console.log('Found registered YearMonth chart, destroying it...');
            existingChart.destroy();
            console.log('Registered YearMonth chart destroyed successfully');
          }
        }
      } catch (error) {
        console.log('Error destroying registered YearMonth chart:', error);
      }

      // Wait for Chart.js to fully clean up the canvas
      setTimeout(() => {
        createYearMonthChart();
      }, 300);
    }

    // Create the YearMonth chart
    function createYearMonthChart() {
      const ctx = document.getElementById('yearMonthChart');
      if (!ctx) {
        console.error('YearMonth chart canvas not found');
        return;
      }

      console.log('Creating YearMonth chart with canvas:', ctx.id, 'dimensions:', ctx.offsetWidth, 'x', ctx.offsetHeight);

      // Clear the canvas completely before creating new chart
      const canvasContext = ctx.getContext('2d');
      if (canvasContext) {
        canvasContext.clearRect(0, 0, ctx.width, ctx.height);
        console.log('YearMonth canvas cleared successfully');
      }

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

      if (datasets.length === 0) {
        console.log('No data available for YearMonth chart');
        return;
      }

      try {
        state.yearMonthChart = new Chart(ctx, {
          type: 'line',
          data: {
            labels: labels,
            datasets: datasets,
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
              title: {
                display: true,
                text: selectedLabel,
                position: 'chartArea',
                align: 'center',
                font: {
                  size: 16,
                  weight: 'bold',
                },
                color: '#000',
              },
              legend: {
                display: true,
                position: 'chartArea',
                align: 'start',
                labels: {
                  boxWidth: 8,
                  padding: 8,
                  font: {
                    size: 10,
                  },
                },
              },
            },
            scales: {
              x: {
                display: true,
                title: {
                  display: true,
                  text: 'Year',
                },
                grid: {
                  display: true,
                  color: 'rgba(0, 0, 0, 0.05)',
                },
              },
              y: {
                display: true,
                title: {
                  display: true,
                  text: selectedLabel,
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
        console.log('YearMonth chart created successfully');
      } catch (error) {
        console.error('Error creating YearMonth chart:', error);
        state.yearMonthChart = null;
      }
    }

    // Format date from YYYY-MM-DD to YYYYMM
    function formatDateToYearMonth(date) {
      if (!date) return '';
      // Convert 2023-10-01 to 202310
      return date.replace('-', '').substring(0, 6);
    }

    // Format month label to show month name (Jan, Feb, etc.)
    function formatMonthLabel(yyyyMmLabel) {
      if (!yyyyMmLabel || yyyyMmLabel.length < 7) return yyyyMmLabel;
      try {
        const parts = yyyyMmLabel.split('-');
        if (parts.length < 2) return yyyyMmLabel;
        const year = parseInt(parts[0]);
        const month = parseInt(parts[1]) - 1; // JS months are 0-indexed
        const date = new Date(year, month, 1);
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return monthNames[date.getMonth()];
      } catch (e) {
        return yyyyMmLabel;
      }
    }

    // Check if we should format labels as month names
    function shouldFormatAsMonths() {
      return state.dataResolution === 'monthly' &&
             (state.timePeriod === 'last_year' ||
              state.timePeriod === 'last_6_months' ||
              state.timePeriod === 'last_3_months' ||
              state.timePeriod === 'select_year');
    }

    // Get series label for display
    function getSeriesLabel(key) {
      const labels = {
        pendingLag_average: "Pending Lag (Average)",
        totalPages_ns0: "Total Pages (NS:0)",
        reviewedPages_ns0: "Reviewed Pages (NS:0)",
        syncedPages_ns0: "Synced Pages (NS:0)",
        pendingChanges: "Pending Changes",
        number_of_reviewers: "Number of Reviewers",
        number_of_reviews: "Number of Reviews",
        reviews_per_reviewer: "Reviews Per Reviewer",
      };
      return labels[key] || key;
    }

    // Filter Wiki table to show data for specific date clicked
    function goToWikiDatePage(date) {
      console.log('Filtering Wiki table for date:', date);
      // Set the filtered date for Wiki mode
      state.filteredWikiDate = date;

      // Update URL to reflect the filtered date
      updateUrl();
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
              position: 'top',
              align: 'center',
              font: {
                size: 16,
                weight: 'bold'
              },
              padding: {
                top: 10,
                bottom: 10
              }
            },
            legend: {
              display: true,
              position: "top",
              align: "start",
              labels: {
                boxWidth: 8,
                padding: 8,
                font: {
                  size: 10
                }
              }
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

    async function updateChart() {
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

      // Initialize charts object if it doesn't exist
      if (!state.charts) {
        state.charts = {};
      }

      // Only destroy charts for series that are now disabled
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

      // Destroy charts for disabled series only
      seriesConfig.forEach(({ key }) => {
        if (!state.series[key] && state.charts[key]) {
          try {
            state.charts[key].destroy();
            delete state.charts[key];
          } catch (error) {
            console.log(`Error destroying disabled chart ${key}:`, error);
            delete state.charts[key];
          }
        }
      });

      if (state.chart) {
        try {
          state.chart.destroy();
        } catch (error) {
          console.log('Error destroying state.chart:', error);
        }
        state.chart = null;
      }


      // Make a simple copy of data to avoid reactivity issues
      const data = JSON.parse(JSON.stringify(state.tableData));
      const selectedWikis = [...state.selectedWikis];

      // Get unique dates based on resolution
      let labels = [];
      if (state.dataResolution === 'yearly') {
        // Extract year only (YYYY)
        labels = [...new Set(data.map(d => d.date.substring(0, 4)))].sort();
      } else if (state.dataResolution === 'daily') {
        // Use full date (YYYY-MM-DD) - but if we have monthly data, we still need to show it
        // Extract all unique dates from the data (only for selected wikis to ensure we have data)
        const relevantData = data.filter(d => selectedWikis.includes(d.wiki));
        labels = [...new Set(relevantData.map(d => d.date))].sort();
        console.log('Daily resolution - extracted labels from relevant data:', labels);
        console.log('Daily resolution - unique dates count:', labels.length);
        console.log('Relevant data entries:', relevantData.length);
        console.log('Sample dates:', relevantData.slice(0, 5).map(d => ({ wiki: d.wiki, date: d.date })));
      } else {
        // Monthly (default) - extract year-month (YYYY-MM)
        labels = [...new Set(data.map(d => d.date.substring(0, 7)))].sort();
      }

      // Keep original labels for data matching, format display labels separately
      const displayLabels = shouldFormatAsMonths()
        ? labels.map(label => formatMonthLabel(label))
        : labels;

      console.log('Labels for charts (resolution: ' + state.dataResolution + '):', labels);
      console.log('Display labels:', displayLabels);

      // Build datasets
      const datasets = [];
      const colors = ["#3273dc", "#48c774", "#ffdd57", "#f14668", "#00d1b2", "#ff3860", "#209cee", "#ff6348"];
      let colorIndex = 0;

      // seriesConfig already defined above - reuse it
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

        // Only create charts for enabled series
        const seriesToRender = seriesConfig.filter(series => state.series[series.key]);

        // Colors are generated dynamically using getWikiColor function

        // Wait for Vue to render all canvas elements
        await nextTick();
        // Give Vue more time to fully render all canvas elements (especially after they were removed)
        await new Promise(resolve => setTimeout(resolve, 300));

        for (const series of seriesToRender) {
          const canvasId = `chart-${series.key}`;

          // Wait a bit and retry if canvas not found (Vue might still be adding it)
          let canvas = document.getElementById(canvasId);
          if (!canvas) {
            // Retry after a delay - Vue might still be rendering
            await new Promise(resolve => setTimeout(resolve, 200));
            canvas = document.getElementById(canvasId);
          }

          console.log(`Looking for canvas: ${canvasId}, found:`, canvas);
          if (!canvas || !canvas.parentElement || typeof canvas.getContext !== 'function') {
            console.log(`Canvas ${canvasId} not found or invalid after retry, skipping`);
            continue;
          }

          const datasets = [];

          selectedWikis.forEach(wiki => {
            // Debug: Check available data for this wiki
            const wikiData = data.filter(d => d.wiki === wiki);
            console.log(`Data for ${wiki}wiki_p:`, wikiData.length, 'entries');
            if (wikiData.length > 0) {
              console.log(`Sample dates for ${wiki}wiki_p:`, wikiData.slice(0, 3).map(d => d.date));
            }

            const seriesData = labels.map((label, index) => {
              // Find entries for this wiki matching the label based on resolution
              // Note: labels are still in YYYY-MM format (not formatted as month names)
              let matchingEntries = [];
              if (state.dataResolution === 'yearly') {
                // Match year (label is YYYY)
                matchingEntries = data.filter(d => d.wiki === wiki && d.date.startsWith(label));
              } else if (state.dataResolution === 'daily') {
                // Exact date match (label is YYYY-MM-DD)
                // Note: Data might be monthly (e.g., "2025-08-01"), which is fine for exact match
                matchingEntries = data.filter(d => d.wiki === wiki && d.date === label);
              } else {
                // Monthly - match year-month (label is YYYY-MM, data dates are YYYY-MM-DD)
                matchingEntries = data.filter(d => d.wiki === wiki && d.date.startsWith(label));
              }

              // Debug for first label attr
              if (index === 0 && series.key === 'pendingLag_average') {
                console.log(`Matching label "${label}" for ${wiki}wiki_p, found ${matchingEntries.length} entries`);
                if (matchingEntries.length > 0) {
                  console.log(`Sample matching entry:`, matchingEntries[0]);
                }
              }

              // For yearly/monthly, take the latest entry; for daily, take the only entry
              if (matchingEntries.length > 0) {
                const entry = matchingEntries.sort((a, b) => b.date.localeCompare(a.date))[0];
                const value = entry ? (entry[series.key] || null) : null;
                if (state.dataResolution === 'daily' && value === null) {
                  console.log(`No value for ${wiki}wiki_p, label ${label}, key ${series.key}, entry:`, entry);
                }
                return value;
              }
              return null;
            });

            // Debug logging for all series, not just pendingLag_average
            console.log(`Series data for ${wiki}wiki_p, ${series.key}:`, seriesData);
            console.log(`Non-null count:`, seriesData.filter(v => v !== null && v !== undefined).length);

            // Debug Pending Lag data specifically
            if (series.key === 'pendingLag_average') {
              console.log(`${wiki}wiki_p Pending Lag data:`, seriesData);
              console.log(`${wiki}wiki_p non-null values:`, seriesData.filter(val => val !== null && val !== undefined));
            }

            if (seriesData.some(val => val !== null && val !== undefined)) {
              datasets.push({
                label: `${wiki}wiki_p`,
                data: seriesData,
                borderColor: getWikiColor(wiki),
                backgroundColor: getWikiColor(wiki) + "20",
                tension: 0.4,
                pointRadius: 0,
                fill: false,
              });
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
            canvas.style.display = 'none';

            // Create a message element if it doesn't exist
            let messageEl = canvas.parentElement.querySelector('.no-data-message');
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
              canvas.parentElement.appendChild(messageEl);
            }
            messageEl.style.display = 'flex';
            continue;
          }

          // Hide any existing no-data message on the fresh canvas
          const messageEl = canvas.parentElement.querySelector('.no-data-message');
          if (messageEl) {
            messageEl.style.display = 'none';
          }
          canvas.style.display = 'block';

          // Destroy any existing chart from state.charts
          if (state.charts[series.key]) {
            try {
              state.charts[series.key].destroy();
            } catch (error) {
              console.log(`Error destroying chart from state for ${canvasId}:`, error);
            }
          }

          // Destroy any chart registered with Chart.js
          try {
            const existingChart = Chart.getChart(canvas);
            if (existingChart) {
              existingChart.destroy();
            }
          } catch (error) {
            console.log(`Error destroying existing chart for ${canvasId}:`, error);
          }

          // Wait for Chart.js cleanup
          await new Promise(resolve => setTimeout(resolve, 50));

          // Ensure canvas and its parent containers are visible
          canvas.style.display = 'block';
          if (canvas.parentElement) {
            canvas.parentElement.style.display = 'block';
          }
          // Traverse up to ensure parent sections are visible
          let parent = canvas.parentElement;
          while (parent && parent !== document.body) {
            if (parent.style && parent.style.display === 'none') {
              parent.style.display = '';
            }
            parent = parent.parentElement;
          }

          // Check dimensions (but be more lenient - as long as parent exists, try to create)
          if (canvas.offsetWidth === 0 && canvas.offsetHeight === 0 && canvas.parentElement) {
            // Try to get dimensions from parent or use defaults
            const parentWidth = canvas.parentElement.offsetWidth || 943;
            const parentHeight = canvas.parentElement.offsetHeight || 500;
            canvas.width = parentWidth;
            canvas.height = parentHeight;
          }

          try {
            state.charts[series.key] = new Chart(canvas, {
              type: 'line',
              data: {
                labels: displayLabels,
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
                  position: 'top',
                  align: 'center',
                  font: {
                    size: 16,
                    weight: 'bold'
                  },
                  padding: {
                    top: 10,
                    bottom: 10
                  }
                },
                legend: {
                  display: true,
                  position: 'chartArea',
                  align: 'center',
                  labels: {
                    boxWidth: 8,
                    padding: 8,
                    font: {
                      size: 10
                    }
                  }
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
                    maxRotation: 45,
                    minRotation: 0,
                    autoSkip: true,
                    maxTicksLimit: 20,
                    callback: function(value, index, ticks) {
                      // Extract date info from the label
                      const dateStr = this.getLabelForValue(value);
                      if (!dateStr) return '';

                      // Parse the date string (could be YYYY-MM or YYYY-MM-DD)
                      const parts = dateStr.split('-');
                      if (parts.length < 2) return dateStr;

                      const year = parts[0];
                      const month = parts[1];

                      // For custom range, show only years (YYYY format)
                      if (state.timePeriod === 'custom') {
                        // Always show first label as year
                        if (index === 0) {
                          return year;
                        }

                        // Show at year boundaries (when year changes)
                        if (index > 0) {
                          const prevDateStr = this.getLabelForValue(ticks[index - 1].value);
                          if (prevDateStr) {
                            const prevYear = prevDateStr.split('-')[0];
                            if (year !== prevYear) {
                              return year; // Show only year for custom range
                            }
                          }
                        }

                        // Also show last label as year
                        if (index === ticks.length - 1) {
                          return year;
                        }

                        return '';
                      }

                      // For select_year, show month names (Jan, Feb, etc.)
                      if (state.timePeriod === 'select_year') {
                        return formatMonthLabel(`${year}-${month}`);
                      }

                      // For preset time periods (last_year, last_6_months, etc.), show year-month format
                      const totalTicks = ticks.length;

                      // Always show first and last
                      if (index === 0 || index === totalTicks - 1) {
                        return `${year}-${month}`;
                      }

                      // Show at year boundaries (when year changes)
                      if (index > 0) {
                        const prevDateStr = this.getLabelForValue(ticks[index - 1].value);
                        if (prevDateStr) {
                          const prevYear = prevDateStr.split('-')[0];
                          if (year !== prevYear) {
                            return `${year}-${month}`; // Show year-month when year changes
                          }
                        }
                      }

                      // For monthly resolution with multiple years, show Jan and Jul of each year
                      if (state.dataResolution === 'monthly' && totalTicks > 12) {
                        if (month === '01' || month === '07') {
                          return `${year}-${month}`;
                        }
                      }

                      // Otherwise, let autoSkip handle it
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
          console.log(`Chart created successfully for ${series.label}, canvas visible: ${canvas.style.display}, dimensions: ${canvas.offsetWidth}x${canvas.offsetHeight}`);
          } catch (error) {
            console.error(`Error creating chart for ${series.label}:`, error);
            // Skip this chart if there's an error
          }
        }
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
                position: 'top',
                align: 'center'
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
                  position: 'top',
                  align: 'center',
                  font: {
                    size: 16,
                    weight: 'bold'
                  },
                  padding: {
                    top: 10,
                    bottom: 10
                  }
                },
                legend: {
                  display: true,
                  position: "top",
                  align: "start",
                  labels: {
                    boxWidth: 8,
                    padding: 8,
                    font: {
                      size: 10
                    }
                  }
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

    // Load full data for chart in YearMonth mode (without month filtering)
    async function loadFullDataForChart() {
      console.log('=== LOADING FULL DATA FOR CHART ===');

      try {
        const promises = [];

        // Build URL parameters for API calls (without month filtering)
        const apiParams = new URLSearchParams();
        // Don't add month filtering for chart data
        apiParams.append('wikis', state.selectedWikis.join(','));

        // Load FlaggedRevs statistics
        promises.push(
          fetch(`/api/flaggedrevs-statistics/?${apiParams.toString()}`)
            .then(response => response.json())
            .then(data => ({ type: 'flaggedrevs', data }))
        );

        // Load review activity
        promises.push(
          fetch(`/api/flaggedrevs-activity/?${apiParams.toString()}`)
            .then(response => response.json())
            .then(data => ({ type: 'activity', data }))
        );

        const results = await Promise.all(promises);

        // Process the data
        let allData = [];
        results.forEach(result => {
          console.log('API result type:', result.type, 'data length:', result.data ? result.data.length : 'undefined');

          // Use same check as working loadData function
          if (result.data) {
            if (result.type === 'flaggedrevs') {
              allData = allData.concat(result.data);
            } else if (result.type === 'activity') {
              allData = allData.concat(result.data);
            }
          }
        });

        console.log('Full data loaded for chart:', allData.length, 'entries');
        console.log('All data sample:', allData.slice(0, 3));

        // Filter out empty objects
        const validData = allData.filter(d => d && Object.keys(d).length > 0);
        console.log('Valid data after filtering:', validData.length, 'entries');

        if (validData.length === 0) {
          console.error('No valid data found for chart');
          return;
        }

        // Now create the chart with the valid data
        createFrsKeyChartWithData(validData);

      } catch (error) {
        console.error('Error loading full data for chart:', error);
        state.error = 'Failed to load chart data';
      }
    }

    // Create FRS Key chart with provided data (for YearMonth mode)
    function createFrsKeyChartWithData(data) {
      console.log('=== CREATING CHART WITH PROVIDED DATA ===');
      console.log('Data length:', data.length);

      // Destroy existing chart first
      if (state.singleChart) {
        try {
          state.singleChart.destroy();
        } catch (error) {
          console.log('Error destroying existing chart:', error);
        }
      }

      // Wait for canvas to be ready
      setTimeout(() => {
        const ctx = document.getElementById('singleFrsKeyChart');
        if (!ctx) {
          console.error('singleFrsKeyChart canvas not found');
          return;
        }

        // Clear canvas
        const canvasContext = ctx.getContext('2d');
        if (canvasContext) {
          canvasContext.clearRect(0, 0, ctx.width, ctx.height);
        }

        // Create chart with the provided data
        createFrsKeyChartWithDataAndCanvas(ctx, data);
      }, 100);
    }

    // Create chart with data and canvas
    function createFrsKeyChartWithDataAndCanvas(ctx, data) {
      console.log('Creating chart with canvas and data...');
      console.log('Raw data sample:', data.slice(0, 3)); // Log first 3 entries to see structure

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
      const selectedWikis = [...state.selectedWikis];
      const labels = [...new Set(data.filter(d => d.yearmonth).map(d => d.yearmonth.toString().substring(0, 4)))].sort();
      console.log('Labels created:', labels);
      console.log('Selected wikis:', selectedWikis);

      // Colors are generated dynamically using getWikiColor function

      const datasets = [];

      selectedWikis.forEach(wiki => {
        const seriesData = labels.map(year => {
          const yearEntries = data.filter(d => d.wiki === wiki && d.yearmonth && d.yearmonth.toString().startsWith(year));
          const latestEntry = yearEntries.sort((a, b) => b.yearmonth - a.yearmonth)[0];
          return latestEntry ? (latestEntry[state.selectedFrsKey] || null) : null;
        });

        if (seriesData.some(val => val !== null && val !== undefined)) {
          datasets.push({
            label: `${wiki}wiki_p`,
            data: seriesData,
            borderColor: getWikiColor(wiki),
            backgroundColor: getWikiColor(wiki) + "20",
            tension: 0.4,
            borderWidth: 3,
            pointRadius: 0,
            fill: false
          });
        }
      });

      if (datasets.length === 0) {
        console.log('No data available for chart');
        return;
      }

      // Create the chart
      state.singleChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: {
            duration: 0
          },
          plugins: {
            title: {
              display: true,
              text: selectedLabel,
              position: 'chartArea',
              align: 'center',
              padding: { top: 0, bottom: 20 },
              font: { size: 16, weight: 'bold' }
            },
            legend: {
              display: true,
              position: 'chartArea',
              align: 'start',
              labels: {
                boxWidth: 8,
                padding: 8,
                font: { size: 10 }
              }
            }
          },
          scales: {
            x: {
              display: true,
              title: {
                display: true,
                text: 'Year'
              }
            },
            y: {
              display: true,
              title: {
                display: true,
                text: selectedLabel
              }
            }
          }
        }
      });

      console.log('Chart created successfully with provided data');
    }

    // Update the single FRS Key chart based on selected metric
    function updateFrsKeyChart() {
      console.log('=== FRS KEY CHART UPDATE DEBUG ===');
      console.log('updateFrsKeyChart called, selectedFrsKey:', state.selectedFrsKey);
      console.log('selectedWikis:', state.selectedWikis);
      console.log('tableData length:', state.tableData.length);
      console.log('filterMode:', state.filterMode);

      // In YearMonth mode, we don't show charts - just redirect
      if (state.filterMode === 'yearmonth') {
        console.log('YearMonth mode - no chart needed');
        return;
      }

      // If no wikis selected or no data, destroy chart and return
      if (state.selectedWikis.length === 0 || state.tableData.length === 0) {
        console.log('No wikis selected or no table data, destroying chart');
        // Destroy existing chart
        if (state.singleChart) {
          try {
            state.singleChart.destroy();
          } catch (error) {
            console.log('Error destroying chart:', error);
          }
          state.singleChart = null;
        }
        // Also destroy any chart that Chart.js might have registered for this canvas
        try {
          const canvas = document.getElementById('singleFrsKeyChart');
          if (canvas) {
            const existingChart = Chart.getChart(canvas);
            if (existingChart) {
              existingChart.destroy();
            }
            // Clear the canvas
            const ctx = canvas.getContext('2d');
            if (ctx) {
              ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
          }
        } catch (error) {
          console.log('Error destroying registered chart:', error);
        }
        return;
      }

      // Create chart immediately without destroying first to avoid blank screen
      createChartAfterDestruction();
    }

    function createChartAfterDestruction() {
      // Destroy existing chart first
      if (state.singleChart) {
        try {
          state.singleChart.destroy();
        } catch (error) {
          console.log('Error destroying chart:', error);
        }
        state.singleChart = null;
      }

      // Also destroy any chart that Chart.js might have registered for this canvas
      try {
        const canvas = document.getElementById('singleFrsKeyChart');
        if (canvas) {
          const existingChart = Chart.getChart(canvas);
          if (existingChart) {
            existingChart.destroy();
          }
        }
      } catch (error) {
        console.log('Error destroying registered chart:', error);
      }

      // Wait for DOM to be ready, especially when switching modes
      setTimeout(() => {
        const ctx = document.getElementById('singleFrsKeyChart');
        if (!ctx) {
          console.log('singleFrsKeyChart canvas not found, retrying...');
          // Retry once more after a longer delay
          setTimeout(() => {
            const retryCtx = document.getElementById('singleFrsKeyChart');
            if (!retryCtx) {
              console.error('singleFrsKeyChart canvas still not found after retry');
              return;
            }
            console.log('Canvas found on retry:', retryCtx);
            createFrsKeyChart(retryCtx);
          }, 200);
          return;
        }

        // Additional check - ensure canvas is visible and has dimensions
        if (ctx.offsetWidth === 0 || ctx.offsetHeight === 0) {
          console.log('Canvas has no dimensions, waiting longer...');
          setTimeout(() => {
            const delayedCtx = document.getElementById('singleFrsKeyChart');
            if (delayedCtx && delayedCtx.offsetWidth > 0 && delayedCtx.offsetHeight > 0) {
              console.log('Canvas ready with dimensions:', delayedCtx.offsetWidth, 'x', delayedCtx.offsetHeight);
              createFrsKeyChart(delayedCtx);
            } else {
              console.error('Canvas still not ready after delay');
            }
          }, 300);
          return;
        }

        console.log('Canvas found and ready:', ctx.offsetWidth, 'x', ctx.offsetHeight);
        createFrsKeyChart(ctx);
      }, 50); // Reduced delay for faster chart updates
    }

    // Create the FRS Key chart
    function createFrsKeyChart(ctx) {
      // Re-fetch canvas first to ensure we have a fresh, valid reference
      const canvas = document.getElementById('singleFrsKeyChart');
      if (!canvas || typeof canvas.getContext !== 'function') {
        console.error('Canvas is not valid for chart creation');
        return;
      }

      // Final safety check - ensure canvas is valid
      if (!canvas || !canvas.parentElement) {
        console.error('Canvas or parent is null, cannot create chart');
        return;
      }

      console.log('Creating chart with canvas:', canvas.id, 'dimensions:', canvas.offsetWidth, 'x', canvas.offsetHeight);

      // Clear the canvas completely before creating new chart
      try {
        const canvasContext = canvas.getContext('2d');
        if (canvasContext) {
          canvasContext.clearRect(0, 0, canvas.width, canvas.height);
          console.log('Canvas cleared successfully');
        }
      } catch (error) {
        console.error('Error clearing canvas:', error);
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
      let data;
      if (state.filterMode === 'yearmonth') {

        data = JSON.parse(JSON.stringify(state.tableData));

        if (data.length === 0) {
          console.log('No data available for YearMonth chart');
          return;
        }
      } else {
        data = JSON.parse(JSON.stringify(state.tableData));
      }
      // Ensure we're using the current selectedWikis from state
      const selectedWikis = [...state.selectedWikis];
      console.log('Creating FRS Key chart with selectedWikis:', selectedWikis);
      console.log('Available data wikis:', [...new Set(data.map(d => d.wiki))]);

      // Get unique dates based on resolution
      let labels = [];
      if (state.dataResolution === 'yearly') {
        labels = [...new Set(data.map(d => d.date.substring(0, 4)))].sort();
      } else if (state.dataResolution === 'daily') {
        labels = [...new Set(data.map(d => d.date))].sort();
      } else {
        // Monthly (default) - extract year-month (YYYY-MM)
        labels = [...new Set(data.map(d => d.date.substring(0, 7)))].sort();
      }

      // Colors are generated dynamically using getWikiColor function

      const datasets = [];

      selectedWikis.forEach(wiki => {
        const seriesData = labels.map(label => {
          // Find entries for this wiki matching the label based on resolution
          let matchingEntries = [];
          if (state.dataResolution === 'yearly') {
            matchingEntries = data.filter(d => d.wiki === wiki && d.date.startsWith(label));
            // For yearly, aggregate all entries in the year
            if (matchingEntries.length > 0) {
              const values = matchingEntries
                .map(e => e[state.selectedFrsKey])
                .filter(v => v !== null && v !== undefined);
              if (values.length > 0) {
                // Calculate average for the year
                const avg = values.reduce((a, b) => a + b, 0) / values.length;
                // For counts/pages, round; for averages, return as float
                if (state.selectedFrsKey === 'pendingLag_average' || state.selectedFrsKey === 'reviews_per_reviewer') {
                  return avg;
                } else {
                  return Math.round(avg);
                }
              }
            }
            return null;
          } else if (state.dataResolution === 'daily') {
            matchingEntries = data.filter(d => d.wiki === wiki && d.date === label);
          } else {
            // Monthly
            matchingEntries = data.filter(d => d.wiki === wiki && d.date.startsWith(label));
          }

          if (matchingEntries.length > 0) {
            const entry = matchingEntries.sort((a, b) => b.date.localeCompare(a.date))[0];
            return entry ? (entry[state.selectedFrsKey] || null) : null;
          }
          return null;
        });

        // Debug: Log the data for each wiki
        console.log(`${wiki}wiki_p ${state.selectedFrsKey} data:`, seriesData);
        console.log(`${wiki}wiki_p non-null values:`, seriesData.filter(val => val !== null && val !== undefined));

        if (seriesData.some(val => val !== null && val !== undefined)) {
          datasets.push({
            label: `${wiki}wiki_p`,
            data: seriesData,
            borderColor: getWikiColor(wiki),
            backgroundColor: getWikiColor(wiki) + "20",
            tension: 0.4,
            borderWidth: 3,
            pointRadius: 0,
            fill: false,
          });
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
        canvas.style.display = 'none';

        // Create a message element if it doesn't exist
        let messageEl = canvas.parentElement.querySelector('.no-data-message');
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
          canvas.parentElement.appendChild(messageEl);
        }
        messageEl.style.display = 'flex';
        return;
      }

      // Hide any existing no-data message
      const messageEl = canvas.parentElement.querySelector('.no-data-message');
      if (messageEl) {
        messageEl.style.display = 'none';
      }

      // Ensure canvas is visible and has valid dimensions
      canvas.style.display = 'block';
      if (canvas.offsetWidth === 0 || canvas.offsetHeight === 0) {
        // Try to get dimensions from parent
        const parentWidth = canvas.parentElement ? canvas.parentElement.offsetWidth : 607;
        const parentHeight = canvas.parentElement ? canvas.parentElement.offsetHeight : 496;
        canvas.width = parentWidth;
        canvas.height = parentHeight;
      }

      // Create the chart
      try {
        state.singleChart = new Chart(canvas, {
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
                position: 'top',
                align: 'center',
                font: {
                  size: 16,
                  weight: 'bold'
                },
                padding: {
                  top: 10,
                  bottom: 10
                }
              },
              legend: {
                display: true,
                position: 'chartArea',
                align: 'center',
                labels: {
                  boxWidth: 8,
                  padding: 8,
                  font: {
                    size: 10
                  }
                }
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
                  maxRotation: 45,
                  minRotation: 0,
                  autoSkip: true,
                  maxTicksLimit: 20,
                  callback: function(value, index, ticks) {
                    // Extract date info from the label
                    const dateStr = this.getLabelForValue(value);
                    if (!dateStr) return '';

                    // Parse the date string (could be YYYY-MM or YYYY-MM-DD)
                    const parts = dateStr.split('-');
                    if (parts.length < 2) return dateStr;

                    const year = parts[0];
                    const month = parts[1];

                    // For custom range, show only years (YYYY format)
                    if (state.timePeriod === 'custom') {
                      // Always show first label as year
                      if (index === 0) {
                        return year;
                      }

                      // Show at year boundaries (when year changes)
                      if (index > 0) {
                        const prevDateStr = this.getLabelForValue(ticks[index - 1].value);
                        if (prevDateStr) {
                          const prevYear = prevDateStr.split('-')[0];
                          if (year !== prevYear) {
                            return year; // Show only year for custom range
                          }
                        }
                      }

                      // Also show last label as year
                      if (index === ticks.length - 1) {
                        return year;
                      }

                      return '';
                    }

                    // For select_year, show month names (Jan, Feb, etc.)
                    if (state.timePeriod === 'select_year') {
                      return formatMonthLabel(`${year}-${month}`);
                    }

                    // For preset time periods (last_year, last_6_months, etc.), show year-month format
                    const totalTicks = ticks.length;

                    // Always show first and last
                    if (index === 0 || index === totalTicks - 1) {
                      return `${year}-${month}`;
                    }

                    // Show at year boundaries (when year changes)
                    if (index > 0) {
                      const prevDateStr = this.getLabelForValue(ticks[index - 1].value);
                      if (prevDateStr) {
                        const prevYear = prevDateStr.split('-')[0];
                        if (year !== prevYear) {
                          return `${year}-${month}`; // Show year-month when year changes
                        }
                      }
                    }

                    // For monthly resolution with multiple years, show Jan and Jul of each year
                    if (state.dataResolution === 'monthly' && totalTicks > 12) {
                      if (month === '01' || month === '07') {
                        return `${year}-${month}`;
                      }
                    }

                    // Otherwise, let autoSkip handle it
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
        console.log('Chart created successfully');
      } catch (error) {
        console.error('Error creating chart:', error);
        state.singleChart = null;
      }
    }

    // Update single wiki chart with customizable metrics
    function updateSingleWikiChart() {
      console.log('=== SINGLE WIKI CHART UPDATE DEBUG ===');
      console.log('selectedSingleWiki:', state.selectedSingleWiki);
      console.log('selected metrics:', state.series);

      if (!state.selectedSingleWiki || state.tableData.length === 0) {
        console.log('No wiki selected or no data available');
        return;
      }

      // Destroy existing chart if it exists
      const canvas = document.getElementById('singleWikiChart');
      if (!canvas) {
        console.log('singleWikiChart canvas not found');
        return;
      }

      try {
        const existingChart = Chart.getChart(canvas);
        if (existingChart) {
          existingChart.destroy();
        }
      } catch (error) {
        console.log('Error destroying existing chart:', error);
      }

      // Get all possible metrics
      const allMetrics = [
        { key: 'pendingChanges', label: 'Pending Changes' },
        { key: 'pendingLag_average', label: 'Pending Lag (Average)' },
        { key: 'totalPages_ns0', label: 'Total Pages (NS:0)' },
        { key: 'reviewedPages_ns0', label: 'Reviewed Pages (NS:0)' },
        { key: 'syncedPages_ns0', label: 'Synced Pages (NS:0)' },
        { key: 'number_of_reviewers', label: 'Number of Reviewers' },
        { key: 'number_of_reviews', label: 'Number of Reviews' },
        { key: 'reviews_per_reviewer', label: 'Reviews Per Reviewer' },
      ];

      // Fixed color mapping for each metric key
      const colorMap = {
        'pendingChanges': '#FF0000',        // Red
        'pendingLag_average': '#00FF00',     // Green
        'totalPages_ns0': '#0000FF',         // Blue
        'reviewedPages_ns0': '#FF00FF',      // Magenta
        'syncedPages_ns0': '#FFFF00',        // Yellow
        'number_of_reviewers': '#FFA500',    // Orange
        'number_of_reviews': '#800080',      // Purple
        'reviews_per_reviewer': '#00FFFF'    // Cyan
      };

      // Get the selected metrics
      const selectedMetrics = allMetrics
        .map(m => ({ ...m, enabled: state.series[m.key] }))
        .filter(m => m.enabled);

      if (selectedMetrics.length === 0) {
        console.log('No metrics selected');
        return;
      }

      // Get data for the selected wiki
      const wikiData = state.tableData.filter(d => d.wiki === state.selectedSingleWiki);
      if (wikiData.length === 0) {
        console.log('No data for selected wiki');
        return;
      }

      // Get unique dates as labels based on resolution
      let labels = [];
      if (state.dataResolution === 'yearly') {
        labels = [...new Set(wikiData.map(d => d.date.substring(0, 4)))].sort();
      } else if (state.dataResolution === 'daily') {
        labels = [...new Set(wikiData.map(d => d.date))].sort();
      } else {
        // Monthly (default) - extract year-month (YYYY-MM)
        labels = [...new Set(wikiData.map(d => d.date.substring(0, 7)))].sort();
      }

      // Separate large and small scale metrics
      const largeScaleMetrics = ['pendingLag_average', 'totalPages_ns0', 'reviewedPages_ns0', 'syncedPages_ns0', 'pendingChanges'];

      const datasets = selectedMetrics.map((metric) => {
        const data = labels.map(label => {
          let matchingEntries = [];
          if (state.dataResolution === 'yearly') {
            matchingEntries = wikiData.filter(d => d.date.startsWith(label));
          } else if (state.dataResolution === 'daily') {
            matchingEntries = wikiData.filter(d => d.date === label);
          } else {
            // Monthly
            matchingEntries = wikiData.filter(d => d.date.startsWith(label));
          }

          if (matchingEntries.length > 0) {
            const entry = matchingEntries.sort((a, b) => b.date.localeCompare(a.date))[0];
            return entry ? (entry[metric.key] || null) : null;
          }
          return null;
        });

        const config = {
          label: metric.label,
          data: data,
          borderColor: colorMap[metric.key],
          backgroundColor: colorMap[metric.key] + "20",
          tension: 0.4,
          pointRadius: 0,
          fill: false,
        };

        // Assign to appropriate Y-axis
        if (largeScaleMetrics.includes(metric.key)) {
          config.yAxisID = 'y';
        } else {
          config.yAxisID = 'y1';
        }

        return config;
      });

      // Create the chart
      try {
        state.singleChart = new Chart(canvas, {
          type: 'line',
          data: { labels, datasets },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: true,
                text: `${state.selectedSingleWiki}wiki_p Metrics`,
                position: 'top',
              },
              legend: {
                display: true,
                position: 'bottom',
                labels: {
                  boxWidth: 10,  // Square boxes (width = height)
                  boxHeight: 10,
                  padding: 5,    // Reduced padding
                  font: {
                    size: 9      // Smaller font
                  }
                }
              },
            },
            scales: {
              y: {
                type: 'linear',
                position: 'left',
                beginAtZero: true,
              },
              y1: {
                type: 'linear',
                position: 'right',
                beginAtZero: true,
                grid: {
                  drawOnChartArea: false,
                },
                ticks: {
                  display: false, // Hide the numbers on the right side
                },
              },
            },
          },
        });
      } catch (error) {
        console.error('Error creating single wiki chart:', error);
      }
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
        } else if (state.timePeriod !== 'all' || state.startDate || state.endDate) {
          // Apply time period filtering (unless already handled by YearMonth mode)
          if (state.startDate) {
            apiParams.set('start_date', state.startDate);
          }
          if (state.endDate) {
            apiParams.set('end_date', state.endDate);
          }
        }
        const queryString = apiParams.toString();

        // Determine which wikis to load data for
        const wikisToLoad = state.filterMode === 'single_wiki' && state.selectedSingleWiki
          ? [state.selectedSingleWiki]
          : state.selectedWikis;

        // Load statistics for each selected wiki
        for (const wiki of wikisToLoad) {
          const statsUrl = `/api/flaggedrevs-statistics/?wiki=${wiki}${queryString ? '&' + queryString : ''}`;
          promises.push(
            fetch(statsUrl)
              .then(response => response.json())
          );

          // Load review activity
          const activityUrl = `/api/flaggedrevs-activity/?wiki=${wiki}${queryString ? '&' + queryString : ''}`;
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
            // Add multiple delays to ensure charts render properly
            setTimeout(() => {
              updateChart();
            }, 500);
          } else if (state.filterMode === 'single_wiki') {
            // For single wiki mode, call updateSingleWikiChart
            await nextTick();
            updateSingleWikiChart();
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

    // Handle time period change
    function handleTimePeriodChange() {
      // Set flag to prevent the date watcher from triggering
      isHandlingTimePeriodChange = true;

      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

      switch (state.timePeriod) {
        case 'all':
          state.startDate = null;
          state.endDate = null;
          break;
        case 'last_year':
          const lastYear = new Date(today);
          lastYear.setFullYear(today.getFullYear() - 1);
          state.startDate = lastYear.toISOString().split('T')[0];
          state.endDate = today.toISOString().split('T')[0];
          // Auto-set resolution to monthly for last year
          state.dataResolution = 'monthly';
          break;
        case 'last_6_months':
          const sixMonthsAgo = new Date(today);
          sixMonthsAgo.setMonth(today.getMonth() - 6);
          state.startDate = sixMonthsAgo.toISOString().split('T')[0];
          state.endDate = today.toISOString().split('T')[0];
          // Auto-set resolution to monthly for 6 months
          state.dataResolution = 'monthly';
          break;
        case 'last_3_months':
          const threeMonthsAgo = new Date(today);
          threeMonthsAgo.setMonth(today.getMonth() - 3);
          state.startDate = threeMonthsAgo.toISOString().split('T')[0];
          state.endDate = today.toISOString().split('T')[0];
          // Auto-set resolution to monthly for 3 months
          state.dataResolution = 'monthly';
          break;
        case 'last_month':
          const lastMonth = new Date(today);
          lastMonth.setMonth(today.getMonth() - 1);
          state.startDate = lastMonth.toISOString().split('T')[0];
          state.endDate = today.toISOString().split('T')[0];
          break;
        case 'custom':
          // Keep existing custom dates, or set defaults
          if (!state.startDate) {
            state.startDate = '2010-01-01';
          }
          if (!state.endDate) {
            state.endDate = today.toISOString().split('T')[0];
          }
          break;
        case 'select_year':
          // If selectedYear is not set, default to current year
          if (!state.selectedYear) {
            state.selectedYear = today.getFullYear();
          }
          const year = state.selectedYear;
          state.startDate = `${year}-01-01`;
          state.endDate = `${year}-12-31`;
          // Auto-set resolution to monthly for selected year
          state.dataResolution = 'monthly';
          break;
      }
      updateUrl();
      loadData();
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

      // Handle selected wiki for single_wiki mode
      if (state.filterMode === 'single_wiki' && state.selectedSingleWiki) {
        params.set('selectedWiki', `${state.selectedSingleWiki}wiki_p`);
      }

      // Handle month selection (only in yearmonth mode)
      if (state.filterMode === 'yearmonth' && state.selectedMonth) {
        // Convert YYYYMM to YYYY-MM format
        const year = state.selectedMonth.substring(0, 4);
        const month = state.selectedMonth.substring(4, 6);
        params.set('month', `${year}-${month}`);
      }

      // Handle time period
      if (state.timePeriod && state.timePeriod !== 'all') {
        params.set('time_period', state.timePeriod);
      }
      if (state.timePeriod === 'select_year' && state.selectedYear) {
        params.set('selected_year', state.selectedYear.toString());
      }
      if (state.startDate) {
        params.set('start_date', state.startDate);
      }
      if (state.endDate) {
        params.set('end_date', state.endDate);
      }

      // Handle data resolution
      if (state.dataResolution && state.dataResolution !== 'monthly') {
        params.set('resolution', state.dataResolution);
      }

      const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
      window.history.replaceState({}, '', newUrl);
    }

    // Load URL parameters on mount
    function loadUrlParams() {
      const params = new URLSearchParams(window.location.search);

      // Handle 'mode' parameter (filter mode)
      const modeParam = params.get('mode');
      if (modeParam && ['wiki', 'frs_key', 'single_wiki', 'yearmonth'].includes(modeParam)) {
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

      // Handle 'wiki' parameter (single wiki for table) - format: fiwiki_p
      const wikiParam = params.get('wiki');
      if (wikiParam) {
        // Remove wiki_p suffix if present
        const wikiCode = wikiParam.endsWith('wiki_p') ? wikiParam.slice(0, -6) : wikiParam;
        const wiki = AVAILABLE_WIKIS.find(aw => aw.code === wikiCode);
        if (wiki) {
          // In Wiki mode, set the table wiki selection, not chart selection
          if (state.filterMode === 'wiki') {
            state.selectedWikiForTable = wikiCode;
          } else if (state.filterMode === 'single_wiki') {
            // In single_wiki mode, set the selected single wiki
            state.selectedSingleWiki = wikiCode;
          } else {
            // In other modes, set chart selection
            state.selectedWikis = [wikiCode];
          }
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

      // Handle 'selectedWiki' parameter for single_wiki mode
      if (state.filterMode === 'single_wiki') {
        const selectedWikiParam = params.get('selectedWiki');
        if (selectedWikiParam) {
          const wikiCode = selectedWikiParam.endsWith('wiki_p') ? selectedWikiParam.slice(0, -6) : selectedWikiParam;
          const wiki = AVAILABLE_WIKIS.find(aw => aw.code === wikiCode);
          if (wiki) {
            state.selectedSingleWiki = wikiCode;
          }
        }
      }

      // Handle 'month' parameter (single month view) - format: 2024-01
      const monthParam = params.get('month');
      if (monthParam && state.filterMode === 'yearmonth') {
        // Convert YYYY-MM to YYYYMM format
        state.selectedMonth = monthParam.replace('-', '');
      }

      // Handle time period
      const timePeriodParam = params.get('time_period');
      if (timePeriodParam) {
        state.timePeriod = timePeriodParam;
      }
      const selectedYearParam = params.get('selected_year');
      if (selectedYearParam && state.timePeriod === 'select_year') {
        const year = parseInt(selectedYearParam);
        if (year >= 2010 && year <= new Date().getFullYear()) {
          state.selectedYear = year;
        }
      }
      const startDateParam = params.get('start_date');
      if (startDateParam) {
        state.startDate = startDateParam;
      }
      const endDateParam = params.get('end_date');
      if (endDateParam) {
        state.endDate = endDateParam;
      }

      // Handle data resolution
      const resolutionParam = params.get('resolution');
      if (resolutionParam && ['yearly', 'monthly', 'daily'].includes(resolutionParam)) {
        state.dataResolution = resolutionParam;
      }

      // If time period is set from URL but dates aren't, calculate them
      if (timePeriodParam && timePeriodParam !== 'all' && timePeriodParam !== 'custom') {
        handleTimePeriodChange();
      }
    }

    // Debounce timer for wiki selection changes
    let wikiSelectionTimeout = null;

    // Flag to prevent double-loading when time period changes
    let isHandlingTimePeriodChange = false;

    // Watchers
    watch(() => state.selectedWikis, async () => {
      console.log('=== SELECTED WIKIS WATCHER DEBUG ===');
      console.log('selectedWikis changed:', state.selectedWikis);
      console.log('selectedWikis length:', state.selectedWikis.length);
      console.log('filterMode:', state.filterMode);

      // Clear any pending timeout
      if (wikiSelectionTimeout) {
        clearTimeout(wikiSelectionTimeout);
      }

      // Debounce the update to prevent rapid-fire calls
      wikiSelectionTimeout = setTimeout(async () => {
        updateUrl();

        // Call the appropriate chart update function based on filter mode
        // Always reload data when wikis change to ensure we have data for newly selected wikis
        await loadData();
      }, 200); // Wait 200ms before updating
    }, { deep: true });

    watch(() => state.selectedMonth, () => {
      updateUrl();
      // Add a small delay to ensure DOM is ready
      setTimeout(() => {
        loadData();
      }, 100);
    });

    // Watch for selected year changes
    watch(() => state.selectedYear, () => {
      if (state.timePeriod === 'select_year') {
        handleTimePeriodChange();
      }
    });

    // Watch for time period changes
    watch(() => state.timePeriod, async () => {
      console.log('Time period changed to:', state.timePeriod);
      if (state.timePeriod === 'select_year' && !state.selectedYear) {
        // Default to current year if no year is selected
        state.selectedYear = new Date().getFullYear();
      }
      if (state.timePeriod !== 'custom') {
        handleTimePeriodChange();
        // handleTimePeriodChange already calls loadData(), so no need to call it again
      } else {
        updateUrl();
      }
    });

    // Watch for date/resolution changes (but not when triggered by handleTimePeriodChange)
    watch(() => [state.startDate, state.endDate, state.dataResolution], () => {
      // Skip if we're already handling time period change (to avoid double loading)
      if (isHandlingTimePeriodChange) {
        isHandlingTimePeriodChange = false;
        return;
      }
      updateUrl();
      // Always reload data when resolution or dates change, even if timePeriod is 'all'
      // This ensures resolution changes update the chart immediately
      loadData();
    }, { deep: true });

    // Watch for series changes to update charts
    watch(() => state.series, async () => {
      if (state.filterMode === 'wiki') {
        // Wait for DOM to fully update, then rebuild charts
        await nextTick();
        // Give Vue more time to render/remove canvas elements
        await new Promise(resolve => setTimeout(resolve, 300));
        updateChart();
      } else if (state.filterMode === 'single_wiki') {
        // Update single wiki chart when metrics change
        await nextTick();
        setTimeout(() => {
          updateSingleWikiChart();
        }, 50);
      }
    }, { deep: true });

    watch(() => state.filterMode, async () => {
      updateUrl();

      // Clear selectedMonth when switching away from YearMonth mode
      if (state.filterMode !== 'yearmonth' && state.selectedMonth) {
        state.selectedMonth = '';
      }

      // Destroy existing charts when switching modes to prevent conflicts
      if (state.charts) {
        Object.values(state.charts).forEach(chart => {
          if (chart) {
            try {
              chart.destroy();
            } catch (e) {
              console.log('Error destroying chart in filterMode watcher:', e);
            }
          }
        });
        state.charts = {};
      }

      // Destroy single chart instances if they exist
      if (state.singleChart) {
        try {
          state.singleChart.destroy();
        } catch (e) {
          console.log('Error destroying singleChart in filterMode watcher:', e);
        }
        state.singleChart = null;
      }

      // Destroy year month chart if it exists
      if (state.yearMonthChart) {
        try {
          state.yearMonthChart.destroy();
        } catch (e) {
          console.log('Error destroying yearMonthChart in filterMode watcher:', e);
        }
        state.yearMonthChart = null;
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

      // Always reload data when switching modes to ensure we have the correct data
      // loadData() will automatically call the appropriate chart update function based on filterMode
      await loadData();
    });

    // Watch for changes to selectedFrsKey and update the chart
    watch(() => state.selectedFrsKey, async () => {
      if (state.filterMode === 'frs_key') {
        updateUrl();
        await nextTick();
        updateFrsKeyChart();
      }
    });

    // Watch for changes to FRS Key metric and update chart (works for both FRS Key and YearMonth)
    watch(() => state.selectedFrsKey, async () => {
      if ((state.filterMode === 'frs_key') || (state.filterMode === 'yearmonth' && state.showGraph)) {
        updateUrl();
        await nextTick();
        updateFrsKeyChart();
      }
    });

    // Watch for changes to selectedSingleWiki and reload data
    watch(() => state.selectedSingleWiki, async () => {
      if (state.filterMode === 'single_wiki') {
        updateUrl();
        await loadData();
        await nextTick();
        updateSingleWikiChart();
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
        const response = await fetch('/api/flaggedrevs-statistics/available-months/');
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
      availableYears,
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
      goToWikiPage,
      goToDatePage,
      goToFrsKey,
      handleTimePeriodChange,
      goToWikiDatePage,
      goToWikiFromDateView,
      goToYearMonthMetric,
      goToYearMonthWiki,
      updateYearMonthChart,
      filteredTableData,

      // Table helper functions
      getFrsKeyValue,
      getSingleDateValue,
      getWikiDateData,
      filteredDateFormatted,
      formatDateToYearMonth,
      getSeriesLabel,
      updateSingleWikiChart,
      loadData,
      refreshData,
      updateUrl,
    };
  }
}).mount('#app');
