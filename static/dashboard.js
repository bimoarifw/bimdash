// Dashboard JavaScript - Real-time monitoring functions

// Global variables for charts and state
let cpuChart, networkChart, diskChart;
let selectedDiskMountpoint = '/';

// Process table sorting state
let currentSortColumn = 'cpu_percent';
let currentSortDirection = 'desc';

const rootElement = document.body;
let pollIntervals = { fastMs: 1000, slowMs: 5000, hiddenMs: 0 };

if (rootElement && rootElement.dataset.pollConfig) {
    try {
        const parsedConfig = JSON.parse(rootElement.dataset.pollConfig);
        if (parsedConfig && typeof parsedConfig === 'object') {
            if (parsedConfig.fast_ms !== undefined) {
                const fastValue = Number(parsedConfig.fast_ms);
                if (Number.isFinite(fastValue) && fastValue > 0) {
                    pollIntervals.fastMs = fastValue;
                }
            }
            if (parsedConfig.slow_ms !== undefined) {
                const slowValue = Number(parsedConfig.slow_ms);
                if (Number.isFinite(slowValue) && slowValue > 0) {
                    pollIntervals.slowMs = slowValue;
                }
            }
            if (parsedConfig.hidden_ms !== undefined) {
                const hiddenValue = Number(parsedConfig.hidden_ms);
                if (Number.isFinite(hiddenValue) && hiddenValue >= 0) {
                    pollIntervals.hiddenMs = hiddenValue;
                }
            }
        }
    } catch (error) {
        console.warn('Failed to parse polling configuration, using defaults.', error);
    }
}

const FAST_POLL_INTERVAL = pollIntervals.fastMs > 0 ? pollIntervals.fastMs : 1000;
const SLOW_POLL_INTERVAL = pollIntervals.slowMs > FAST_POLL_INTERVAL ? pollIntervals.slowMs : FAST_POLL_INTERVAL;
const HIDDEN_POLL_INTERVAL = pollIntervals.hiddenMs > 0 ? pollIntervals.hiddenMs : 0;

// Update processes table
async function updateProcessesTable(sortColumn = currentSortColumn, sortDirection = currentSortDirection) {
    try {
        const response = await fetch('/api/processes');
        let processes = await response.json();

        // Sort the processes
        processes.sort((a, b) => {
            let aValue = a[sortColumn];
            let bValue = b[sortColumn];

            // Handle string sorting for name
            if (sortColumn === 'name') {
                aValue = aValue.toLowerCase();
                bValue = bValue.toLowerCase();
            }

            if (sortDirection === 'asc') {
                return aValue > bValue ? 1 : aValue < bValue ? -1 : 0;
            } else {
                return aValue < bValue ? 1 : aValue > bValue ? -1 : 0;
            }
        });

        const tbody = document.querySelector('#processes-table tbody');
        tbody.innerHTML = '';

        processes.forEach(process => {
            const row = document.createElement('tr');
            row.className = 'hover:bg-gray-50 transition-colors duration-200';

            // Determine color classes based on CPU and memory usage
            const cpuClass = process.cpu_percent > 50 ? 'bg-red-100 text-red-800' :
                process.cpu_percent > 20 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-green-100 text-green-800';
            const memoryClass = process.memory_percent > 50 ? 'bg-red-100 text-red-800' :
                process.memory_percent > 20 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-green-100 text-green-800';

            row.innerHTML = `
                <td class="px-3 sm:px-6 py-3 sm:py-4 whitespace-nowrap">
                    <div class="flex items-center">
                        <div class="flex-shrink-0 w-8 h-8 sm:w-10 sm:h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                            <span class="text-white font-bold text-xs sm:text-sm">${process.name.substring(0, 2).toUpperCase()}</span>
                        </div>
                        <div class="ml-3 sm:ml-4">
                            <div class="text-sm font-medium text-gray-900 truncate max-w-24 sm:max-w-none">
                                ${process.name.substring(0, 25)}${process.name.length > 25 ? '...' : ''}
                            </div>
                        </div>
                    </div>
                </td>
                <td class="px-3 sm:px-6 py-3 sm:py-4 whitespace-nowrap text-sm text-gray-500 hidden sm:table-cell">
                    ${process.pid}
                </td>
                <td class="px-3 sm:px-6 py-3 sm:py-4 whitespace-nowrap">
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cpuClass}">
                        ${process.cpu_percent.toFixed(1)}%
                    </span>
                </td>
                <td class="px-3 sm:px-6 py-3 sm:py-4 whitespace-nowrap">
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${memoryClass}">
                        ${process.memory_percent.toFixed(1)}%
                    </span>
                </td>
                <td class="px-3 sm:px-6 py-3 sm:py-4 whitespace-nowrap text-sm text-gray-500 hidden md:table-cell">
                    ${process.memory_mb.toFixed(1)}
                </td>
            `;
            tbody.appendChild(row);
        });

        // Update sort indicators
        updateSortIndicators(sortColumn, sortDirection);

    } catch (error) {
        console.error('Error updating processes table:', error);
    }
}

// Update sort indicators
function updateSortIndicators(sortColumn, sortDirection) {
    // Reset all headers
    document.querySelectorAll('.sort-header').forEach(header => {
        const icon = header.querySelector('.sort-icon');
        icon.classList.add('opacity-0');
        icon.classList.remove('opacity-100', 'text-blue-600');
        icon.classList.add('text-gray-400');
        icon.style.transform = 'rotate(0deg)';
        header.classList.remove('text-blue-600');
        header.classList.add('text-gray-600');
    });

    // Update active column
    const activeHeader = document.querySelector(`[data-sort="${sortColumn}"]`);
    if (activeHeader) {
        const icon = activeHeader.querySelector('.sort-icon');
        icon.classList.remove('opacity-0', 'text-gray-400');
        icon.classList.add('opacity-100', 'text-blue-600');
        activeHeader.classList.remove('text-gray-600');
        activeHeader.classList.add('text-blue-600');

        // Rotate icon based on sort direction
        if (sortDirection === 'asc') {
            icon.style.transform = 'rotate(180deg)';
        } else {
            icon.style.transform = 'rotate(0deg)';
        }
    }
}

// Handle column header clicks for sorting
function initializeProcessSorting() {
    document.querySelectorAll('.sort-header').forEach(header => {
        header.addEventListener('click', function () {
            const sortColumn = this.getAttribute('data-sort');

            // Toggle sort direction if same column, otherwise set to desc
            if (currentSortColumn === sortColumn) {
                currentSortDirection = currentSortDirection === 'desc' ? 'asc' : 'desc';
            } else {
                currentSortColumn = sortColumn;
                currentSortDirection = 'desc'; // Default to descending for new columns
            }

            // Update table immediately
            updateProcessesTable(currentSortColumn, currentSortDirection);
        });
    });
}

// Update docker table
async function updateDockerTable() {
    try {
        const response = await fetch('/api/metrics');
        const data = await response.json();
        const containers = data.docker;

        const tbody = document.querySelector('#docker-table tbody');
        tbody.innerHTML = '';

        containers.forEach(container => {
            const statusClass = container.status === 'running' ? 'running' :
                container.status === 'exited' ? 'stopped' : 'paused';

            // Main row with all columns
            const mainRow = document.createElement('tr');
            mainRow.className = 'hover:bg-gray-50 transition-colors duration-200';
            mainRow.innerHTML = `
                <td class="px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm">
                    <div class="flex items-center">
                        <div class="flex-shrink-0 w-6 h-6 sm:w-8 sm:h-8 bg-gradient-to-r from-blue-500 to-purple-500 rounded-lg flex items-center justify-center mr-2 sm:mr-3">
                            <svg class="w-3 h-3 sm:w-4 sm:h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"></path>
                            </svg>
                        </div>
                        <div>
                            <div class="font-mono text-gray-900 font-medium text-xs sm:text-sm">${container.id.substring(0, 8)}<span class="hidden sm:inline">${container.id.substring(8, 12)}</span></div>
                            <div class="text-xs text-gray-500 hidden sm:block">Container</div>
                        </div>
                    </div>
                </td>
                <td class="px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm">
                    <div class="flex items-center">
                        <div class="flex-shrink-0 w-6 h-6 sm:w-8 sm:h-8 bg-gradient-to-r from-green-500 to-teal-500 rounded-lg flex items-center justify-center mr-2 sm:mr-3">
                            <svg class="w-3 h-3 sm:w-4 sm:h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path>
                            </svg>
                        </div>
                        <div>
                            <div class="font-medium text-gray-900 truncate max-w-16 sm:max-w-24 lg:max-w-none text-xs sm:text-sm">${container.name}</div>
                            <div class="text-xs text-gray-500 hidden sm:block">Service</div>
                        </div>
                    </div>
                </td>
                <td class="px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap">
                    <span class="inline-flex items-center px-1.5 sm:px-2.5 py-0.5 rounded-full text-xs font-medium
                        ${container.status === 'running' ? 'bg-green-100 text-green-800' :
                    container.status === 'exited' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'}">
                        <span class="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full mr-1 sm:mr-2
                            ${container.status === 'running' ? 'bg-green-400' :
                    container.status === 'exited' ? 'bg-red-400' :
                        'bg-yellow-400'}"></span>
                        <span class="hidden sm:inline">${container.status.charAt(0).toUpperCase() + container.status.slice(1)}</span>
                        <span class="sm:hidden">${container.status === 'running' ? 'Run' : container.status === 'exited' ? 'Stop' : 'Pause'}</span>
                    </span>
                </td>
                <td class="px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm text-gray-500 hidden md:table-cell">
                    <div class="flex items-center">
                        <div class="flex-shrink-0 w-5 h-5 sm:w-6 sm:h-6 bg-gradient-to-r from-purple-500 to-pink-500 rounded-md flex items-center justify-center mr-1 sm:mr-2">
                            <svg class="w-2.5 h-2.5 sm:w-3 sm:h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
                            </svg>
                        </div>
                        <span class="truncate max-w-20 sm:max-w-32 text-xs sm:text-sm">${container.image}</span>
                    </div>
                </td>
                <!-- Hidden detail columns -->
                <td class="docker-detail-column px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm text-center hidden">
                    ${container.cpu_percent ? `<span class="${container.cpu_percent > 80 ? 'text-red-600' : container.cpu_percent > 50 ? 'text-yellow-600' : 'text-gray-900'} font-medium">${container.cpu_percent.toFixed(1)}%</span>` : '<span class="text-gray-400">N/A</span>'}
                </td>
                <td class="docker-detail-column px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm text-center hidden">
                    ${container.mem_usage && container.mem_limit ? `
                        <div class="text-gray-900 font-medium">${(container.mem_usage / (1024 ** 2)).toFixed(1)}MB</div>
                        <div class="text-xs text-gray-500">/ ${(container.mem_limit / (1024 ** 2)).toFixed(1)}MB</div>
                    ` : '<span class="text-gray-400">N/A</span>'}
                </td>
                <td class="docker-detail-column px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm text-center hidden">
                    ${container.mem_percent ? `<span class="${container.mem_percent > 80 ? 'text-red-600' : container.mem_percent > 60 ? 'text-yellow-600' : 'text-gray-900'} font-medium">${container.mem_percent.toFixed(1)}%</span>` : '<span class="text-gray-400">N/A</span>'}
                </td>
                <td class="docker-detail-column px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm text-center hidden">
                    ${container.net_rx !== undefined && container.net_tx !== undefined ? `
                        <div class="flex flex-col items-center space-y-0.5 sm:space-y-1">
                            <div class="flex items-center text-green-600 text-xs">
                                <svg class="w-2.5 h-2.5 sm:w-3 sm:h-3 mr-0.5 sm:mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16l-4-4m0 0l4-4m-4 4h18"></path>
                                </svg>
                                ${(container.net_rx / (1024 ** 2)).toFixed(1)}MB
                            </div>
                            <div class="flex items-center text-blue-600 text-xs">
                                <svg class="w-2.5 h-2.5 sm:w-3 sm:h-3 mr-0.5 sm:mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H3"></path>
                                </svg>
                                ${(container.net_tx / (1024 ** 2)).toFixed(1)}MB
                            </div>
                        </div>
                    ` : '<span class="text-gray-400">N/A</span>'}
                </td>
                <td class="docker-detail-column px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm text-center hidden">
                    ${container.blk_read !== undefined && container.blk_write !== undefined ? `
                        <div class="flex flex-col items-center space-y-0.5 sm:space-y-1">
                            <div class="flex items-center text-blue-600 text-xs">
                                <svg class="w-2.5 h-2.5 sm:w-3 sm:h-3 mr-0.5 sm:mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16l-4-4m0 0l4-4m-4 4h18"></path>
                                </svg>
                                ${(container.blk_read / (1024 ** 2)).toFixed(1)}MB
                            </div>
                            <div class="flex items-center text-red-600 text-xs">
                                <svg class="w-2.5 h-2.5 sm:w-3 sm:h-3 mr-0.5 sm:mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H3"></path>
                                </svg>
                                ${(container.blk_write / (1024 ** 2)).toFixed(1)}MB
                            </div>
                        </div>
                    ` : '<span class="text-gray-400">N/A</span>'}
                </td>
                <td class="docker-detail-column px-1 sm:px-2 lg:px-3 py-2 sm:py-3 lg:py-4 whitespace-nowrap text-xs sm:text-sm text-center hidden">
                    ${container.pids ? `<span class="text-gray-900 font-medium">${container.pids}</span>` : '<span class="text-gray-400">N/A</span>'}
                </td>
            `;
            tbody.appendChild(mainRow);
        });

        // Set initial state based on current visibility
        const detailColumns = document.querySelectorAll('.docker-detail-column');
        const shrinkColumns = document.querySelectorAll('.docker-shrink-column');
        if (detailColumns.length > 0) {
            // Check if button is in expanded state
            const desktopButton = document.getElementById('docker-expand-toggle');
            const mobileButton = document.getElementById('docker-expand-toggle-mobile');
            const isExpanded = desktopButton && desktopButton.getAttribute('data-expanded') === 'true';

            if (isExpanded) {
                // Keep detail columns visible
                detailColumns.forEach(column => {
                    column.classList.remove('hidden');
                    column.style.opacity = '1';
                    column.style.transform = 'scaleX(1)';
                    column.style.maxWidth = '';
                });

                // Keep columns shrunk
                shrinkColumns.forEach(column => {
                    if (column.textContent.includes('ID') || column.textContent.includes('#')) {
                        column.style.width = '60px';
                    } else if (column.textContent.includes('Name')) {
                        column.style.width = '100px';
                    } else if (column.textContent.includes('Status') || column.textContent.includes('Stat')) {
                        column.style.width = '80px';
                    } else if (column.textContent.includes('Image') || column.textContent.includes('Img')) {
                        column.style.width = '120px';
                    }
                });

                // Ensure buttons show expanded state
                if (desktopButton) {
                    desktopButton.setAttribute('data-expanded', 'true');
                    const icon = desktopButton.querySelector('svg');
                    const text = document.getElementById('expand-text');
                    if (icon) icon.style.transform = 'rotate(180deg)';
                    if (text) text.textContent = 'Hide Details';
                    desktopButton.className = desktopButton.className.replace(/from-blue-500 to-purple-600/g, 'from-purple-500 to-pink-600');
                    desktopButton.className = desktopButton.className.replace(/hover:from-blue-600 hover:to-purple-700/g, 'hover:from-purple-600 hover:to-pink-700');
                }
                if (mobileButton) {
                    mobileButton.setAttribute('data-expanded', 'true');
                    const icon = mobileButton.querySelector('svg');
                    if (icon) icon.style.transform = 'rotate(180deg)';
                    mobileButton.className = mobileButton.className.replace(/from-blue-500 to-purple-600/g, 'from-purple-500 to-pink-600');
                    mobileButton.className = mobileButton.className.replace(/hover:from-blue-600 hover:to-purple-700/g, 'hover:from-purple-600 hover:to-pink-700');
                }
            } else {
                // Keep detail columns hidden
                detailColumns.forEach(column => {
                    column.classList.add('hidden');
                    column.style.opacity = '';
                    column.style.transform = '';
                    column.style.maxWidth = '';
                });

                // Restore original column widths
                shrinkColumns.forEach(column => {
                    column.style.width = '';
                });

                // Ensure buttons show collapsed state
                if (desktopButton) {
                    desktopButton.setAttribute('data-expanded', 'false');
                    const icon = desktopButton.querySelector('svg');
                    const text = document.getElementById('expand-text');
                    if (icon) icon.style.transform = 'rotate(0deg)';
                    if (text) text.textContent = 'Show Details';
                    desktopButton.className = desktopButton.className.replace(/from-purple-500 to-pink-600/g, 'from-blue-500 to-purple-600');
                    desktopButton.className = desktopButton.className.replace(/hover:from-purple-600 hover:to-pink-700/g, 'hover:from-blue-600 hover:to-purple-700');
                }
                if (mobileButton) {
                    mobileButton.setAttribute('data-expanded', 'false');
                    const icon = mobileButton.querySelector('svg');
                    if (icon) icon.style.transform = 'rotate(0deg)';
                    mobileButton.className = mobileButton.className.replace(/from-purple-500 to-pink-600/g, 'from-blue-500 to-purple-600');
                    mobileButton.className = mobileButton.className.replace(/hover:from-purple-600 hover:to-pink-700/g, 'hover:from-blue-600 hover:to-purple-700');
                }
            }
        }
    } catch (error) {
        console.error('Error updating docker table:', error);
    }
}

// Initialize Docker expand button event listener
function initializeDockerExpandButton() {
    // Handle both mobile and desktop buttons
    const desktopButton = document.getElementById('docker-expand-toggle');
    const mobileButton = document.getElementById('docker-expand-toggle-mobile');

    // Initialize state if not set
    if (!desktopButton.hasAttribute('data-expanded')) {
        desktopButton.setAttribute('data-expanded', 'false');
    }
    if (!mobileButton.hasAttribute('data-expanded')) {
        mobileButton.setAttribute('data-expanded', 'false');
    }

    // Function to update button appearance
    function updateButtonAppearance(button, isExpanded) {
        const icon = button.querySelector('svg');
        const text = button.id === 'docker-expand-toggle' ? document.getElementById('expand-text') : null;

        if (isExpanded) {
            // Expanded state: purple-pink gradient
            button.className = button.className.replace(/from-blue-500 to-purple-600|from-purple-500 to-pink-600/g, 'from-purple-500 to-pink-600');
            button.className = button.className.replace(/hover:from-blue-600 hover:to-purple-700|hover:from-purple-600 hover:to-pink-700/g, 'hover:from-purple-600 hover:to-pink-700');

            if (icon) {
                icon.style.transform = 'rotate(180deg)';
            }
            if (text) {
                text.textContent = 'Hide Details';
            }
        } else {
            // Collapsed state: blue-purple gradient
            button.className = button.className.replace(/from-purple-500 to-pink-600|from-blue-500 to-purple-600/g, 'from-blue-500 to-purple-600');
            button.className = button.className.replace(/hover:from-purple-600 hover:to-pink-700|hover:from-blue-600 hover:to-purple-700/g, 'hover:from-blue-600 hover:to-purple-700');

            if (icon) {
                icon.style.transform = 'rotate(0deg)';
            }
            if (text) {
                text.textContent = 'Show Details';
            }
        }
    }

    // Function to handle expand/collapse
    function toggleExpansion() {
        const detailColumns = document.querySelectorAll('.docker-detail-column');
        const shrinkColumns = document.querySelectorAll('.docker-shrink-column');
        const isExpanded = desktopButton.getAttribute('data-expanded') === 'true';

        if (isExpanded) {
            // Hide columns with smooth animation - start from current visible state
            detailColumns.forEach(column => {
                // Ensure columns are visible before animating out
                column.classList.remove('hidden');
                column.style.opacity = '1';
                column.style.transform = 'scaleX(1)';
                column.style.maxWidth = column.offsetWidth + 'px';
                column.style.transition = 'opacity 0.3s ease-in-out, transform 0.3s ease-in-out, max-width 0.3s ease-in-out';
            });

            // Start the collapse animation after a brief delay
            setTimeout(() => {
                detailColumns.forEach(column => {
                    column.style.opacity = '0';
                    column.style.transform = 'scaleX(0)';
                    column.style.maxWidth = '0px';
                });
            }, 10);

            // Clean up after animation completes
            setTimeout(() => {
                detailColumns.forEach(column => {
                    column.classList.add('hidden');
                    column.style.opacity = '';
                    column.style.transform = '';
                    column.style.transition = '';
                    column.style.maxWidth = '';
                });
            }, 320); // 10ms delay + 300ms animation + 10ms buffer

            // Restore original column widths with smooth transition
            setTimeout(() => {
                shrinkColumns.forEach(column => {
                    column.style.transition = 'width 0.3s ease-in-out';
                    column.style.width = '';
                });
            }, 50);

            // Update state and appearance immediately
            desktopButton.setAttribute('data-expanded', 'false');
            mobileButton.setAttribute('data-expanded', 'false');
            updateButtonAppearance(desktopButton, false);
            updateButtonAppearance(mobileButton, false);
        } else {
            // Show columns with smooth animation
            detailColumns.forEach(column => {
                column.classList.remove('hidden');
                column.style.opacity = '0';
                column.style.transform = 'scaleX(0)';
                column.style.maxWidth = '0px';
                column.style.transition = 'opacity 0.3s ease-in-out, transform 0.3s ease-in-out, max-width 0.3s ease-in-out';
            });

            setTimeout(() => {
                detailColumns.forEach(column => {
                    column.style.opacity = '1';
                    column.style.transform = 'scaleX(1)';
                    column.style.maxWidth = '';
                });
            }, 10);

            // Shrink certain columns to make room for detail columns
            setTimeout(() => {
                shrinkColumns.forEach(column => {
                    column.style.transition = 'width 0.3s ease-in-out';
                    if (column.textContent.includes('ID') || column.textContent.includes('#')) {
                        column.style.width = '60px';
                    } else if (column.textContent.includes('Name')) {
                        column.style.width = '100px';
                    } else if (column.textContent.includes('Status') || column.textContent.includes('Stat')) {
                        column.style.width = '80px';
                    } else if (column.textContent.includes('Image') || column.textContent.includes('Img')) {
                        column.style.width = '120px';
                    }
                });
            }, 10);

            // Update state and appearance
            desktopButton.setAttribute('data-expanded', 'true');
            mobileButton.setAttribute('data-expanded', 'true');
            updateButtonAppearance(desktopButton, true);
            updateButtonAppearance(mobileButton, true);
        }
    }

    // Add event listeners to both buttons
    if (desktopButton) {
        desktopButton.addEventListener('click', toggleExpansion);
    }
    if (mobileButton) {
        mobileButton.addEventListener('click', toggleExpansion);
    }
}

// Main refresh data function
async function refreshFastData() {
    try {
        const response = await fetch('/api/overview');
        const data = await response.json();

        // Update CPU chart
        const now = new Date();
        if (window.cpuChart) {
            window.cpuChart.data.labels.push(now);
            window.cpuChart.data.datasets[0].data.push(data.cpu.overall_percent);
            if (window.cpuChart.data.labels.length > 20) {
                window.cpuChart.data.labels.shift();
                window.cpuChart.data.datasets[0].data.shift();
            }
            window.cpuChart.update();
        }

        // Update CPU per core chart
        if (window.cpuPerCoreChart) {
            window.cpuPerCoreChart.data.datasets[0].data = data.cpu.per_core_percent;
            window.cpuPerCoreChart.update();
        }

        // Update system overview cards for CPU and uptime
        if (data.uptime) {
            // Update uptime
            const uptimeElements = document.querySelectorAll('dt');
            uptimeElements.forEach(dt => {
                if (dt.textContent.includes('System Uptime')) {
                    const dd = dt.nextElementSibling;
                    if (dd && dd.tagName === 'DD') {
                        dd.textContent = data.uptime.uptime_formatted;
                        const bootTimeElement = dd.nextElementSibling;
                        if (bootTimeElement && bootTimeElement.tagName === 'DD') {
                            bootTimeElement.textContent = 'Since ' + data.uptime.boot_time;
                        }
                    }
                }
                // Update load average
                if (dt.textContent.includes('Load Average')) {
                    const dd = dt.nextElementSibling;
                    if (dd && dd.tagName === 'DD' && data.uptime.load_average) {
                        dd.textContent = data.uptime.load_average[0].toFixed(1);
                    }
                }
                // Update CPU usage
                if (dt.textContent.includes('CPU Usage')) {
                    const dd = dt.nextElementSibling;
                    if (dd && dd.tagName === 'DD') {
                        dd.textContent = data.cpu.overall_percent.toFixed(1) + '%';
                        // Update progress bar
                        const progressBar = dd.parentElement.parentElement.parentElement.querySelector('.bg-gradient-to-r.h-3');
                        if (progressBar) {
                            progressBar.style.width = data.cpu.overall_percent + '%';
                        }
                    }
                }
            });
        }

        // Update memory
        if (data.memory) {
            const memoryElements = document.querySelectorAll('dt');
            memoryElements.forEach(dt => {
                if (dt.textContent.includes('Memory Usage')) {
                    const dd = dt.nextElementSibling;
                    if (dd && dd.tagName === 'DD') {
                        dd.textContent = `${data.memory.percent.toFixed(1)}% (${(data.memory.used / (1024 ** 3)).toFixed(1)} GB / ${(data.memory.total / (1024 ** 3)).toFixed(1)} GB)`;
                        // Update progress bar
                        const progressBar = dd.parentElement.parentElement.parentElement.querySelector('.bg-gradient-to-r.h-3');
                        if (progressBar) {
                            progressBar.style.width = data.memory.percent + '%';
                        }
                    }
                }
            });
        }

        // Update RAM percentage
        if (data.memory && data.memory.virtual) {
            const ramPercentage = document.getElementById('ram-percentage');
            if (ramPercentage) {
                ramPercentage.textContent = data.memory.virtual.percent.toFixed(1) + '% Used';
            }
            // Update progress bar
            const memoryProgressBar = document.getElementById('memory-progress-bar');
            if (memoryProgressBar) {
                memoryProgressBar.style.width = data.memory.virtual.percent + '%';
            }
        }

        // Update memory chart
        if (data.memory && data.memory.virtual && window.memoryChart) {
            const usedGB = data.memory.virtual.used / (1024 ** 3);
            const availableGB = data.memory.virtual.available / (1024 ** 3);
            window.memoryChart.data.datasets[0].data = [usedGB, availableGB];
            window.memoryChart.update();
        }

    } catch (error) {
        console.error('Error refreshing fast data:', error);
    }
}

async function refreshSlowData() {
    try {
        // Update network
        const networkResponse = await fetch('/api/network');
        const networkData = await networkResponse.json();

        // Update network chart
        if (window.networkChart) {
            const now = new Date();
            window.networkChart.data.labels.push(now);
            window.networkChart.data.datasets[0].data.push(networkData.bytes_sent / (1024 * 1024));
            window.networkChart.data.datasets[1].data.push(networkData.bytes_recv / (1024 * 1024));
            if (window.networkChart.data.labels.length > 20) {
                window.networkChart.data.labels.shift();
                window.networkChart.data.datasets[0].data.shift();
                window.networkChart.data.datasets[1].data.shift();
            }
            window.networkChart.update();
        }

        // Update disk
        const diskResponse = await fetch('/api/disk');
        const diskData = await diskResponse.json();
        const partitions = Array.isArray(diskData?.partitions) ? diskData.partitions : Array.isArray(diskData) ? diskData : [];

        if (window.diskChart && partitions.length > 0) {
            const selectedPartition = partitions.find(p => p.mountpoint === window.selectedDiskMountpoint) || partitions[0];
            window.diskChart.data.datasets[0].data = [selectedPartition.used, selectedPartition.free];
            window.diskChart.update();
        }

        // Update docker
        const dockerResponse = await fetch('/api/docker');
        const dockerData = await dockerResponse.json();

        // Update Docker containers count
        const dockerElements = document.querySelectorAll('dt');
        dockerElements.forEach(dt => {
            if (dt.textContent.includes('Docker Containers')) {
                const dd = dt.nextElementSibling;
                if (dd && dd.tagName === 'DD') {
                    dd.textContent = dockerData.length;
                }
            }
        });

        // Update tables
        await updateProcessesTable();
        await updateDockerTable();

    } catch (error) {
        console.error('Error refreshing slow data:', error);
    }
}

async function refreshData() {
    await refreshFastData();
    await refreshSlowData();
}

// Polling system
let fastRefreshHandle = null;
let slowRefreshHandle = null;

function stopPolling() {
    if (fastRefreshHandle) {
        clearInterval(fastRefreshHandle);
        fastRefreshHandle = null;
    }
    if (slowRefreshHandle) {
        clearInterval(slowRefreshHandle);
        slowRefreshHandle = null;
    }
}

function schedulePolling(immediate = false) {
    stopPolling();
    const isVisible = document.visibilityState === 'visible';

    if (isVisible) {
        if (immediate) {
            refreshFastData();
            refreshSlowData();
        }
        fastRefreshHandle = setInterval(refreshFastData, FAST_POLL_INTERVAL);
        slowRefreshHandle = setInterval(refreshSlowData, SLOW_POLL_INTERVAL);
        return;
    }

    if (HIDDEN_POLL_INTERVAL > 0) {
        if (immediate) {
            refreshFastData();
        }
        fastRefreshHandle = setInterval(refreshFastData, HIDDEN_POLL_INTERVAL);
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            schedulePolling(true);
        } else if (HIDDEN_POLL_INTERVAL > 0) {
            schedulePolling(false);
        } else {
            stopPolling();
        }
    });

    window.addEventListener('focus', function () {
        if (document.visibilityState === 'visible') {
            schedulePolling(true);
        }
    });

    window.addEventListener('blur', function () {
        if (document.visibilityState !== 'visible') {
            if (HIDDEN_POLL_INTERVAL > 0) {
                schedulePolling(false);
            } else {
                stopPolling();
            }
        }
    });

    schedulePolling(true);

    updateProcessesTable();
    initializeProcessSorting();
    updateDockerTable();
    initializeDockerExpandButton();

    setTimeout(() => {
        refreshData();
    }, FAST_POLL_INTERVAL);
});