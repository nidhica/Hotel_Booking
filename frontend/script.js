const API_BASE_URL = "";
let currentUser = null;
let allRooms = [];
let currentBookings = [];
let selectedRoom = null;
let bookingPrefill = null;
let availabilityRefreshTimer = null;
let lastSuccessfulBookingId = null;
let selectedCompareRoomIds = [];
let currentPriceFilter = 10000;
let minPriceFilter = 0;
let roomPagination = { page: 1, page_size: 6, total_items: 0, total_pages: 1 };
let roomFilterOptions = { locations: [], amenities: [], price_bounds: { min: 0, max: 10000 } };
let roomFiltersInitialized = false;
let roomReviewsById = {};
let analyticsCharts = {};
const roomSearchState = {
  page: 1,
  pageSize: 6,
  minPrice: 0,
  maxPrice: 10000,
  location: "",
  rating: "",
  amenities: [],
};
const availabilityState = {
  booking: { blockedDates: new Set(), roomId: null, calendarDays: [] },
  edit: { blockedDates: new Set(), roomId: null, excludeBookingId: null, calendarDays: [] },
};

async function handleLogin(event) {
  event.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;

  if (!email || !password) {
    alert("Please enter email and password.");
    return;
  }

  try {
    const data = await fetchJson(`${API_BASE_URL}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    currentUser = data.user;
    localStorage.setItem("currentUser", JSON.stringify(data.user));
    showMainApp();
  } catch (error) {
    alert("Login failed: " + error.message);
  }
}

async function handleSignup(event) {
  event.preventDefault();
  const name = document.getElementById("signup-name").value.trim();
  const phone = document.getElementById("signup-phone").value.trim();
  const email = document.getElementById("signup-email").value.trim();
  const password = document.getElementById("signup-password").value;

  try {
    await fetchJson(`${API_BASE_URL}/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, phone, email, password }),
    });
    alert("Account created! Please log in.");
    toggleAuthForm();
  } catch (error) {
    alert("Signup failed: " + error.message);
  }
}

function toggleAuthForm(event) {
  if (event) event.preventDefault();
  document.getElementById("login-form").classList.toggle("active");
  document.getElementById("signup-form").classList.toggle("active");
}

function showMainApp() {
  document.getElementById("auth-page").classList.remove("active");
  document.getElementById("app-container").classList.add("active");
  document.getElementById("user-info").textContent = `${currentUser.role.toUpperCase()} | ${currentUser.full_name}`;

  if (currentUser.role === "admin") {
    stopAvailabilityRefresh();
    document.getElementById("customer-dashboard").style.display = "none";
    document.getElementById("admin-dashboard").style.display = "block";
    loadAdminAnalytics();
  } else {
    document.getElementById("customer-dashboard").style.display = "block";
    document.getElementById("admin-dashboard").style.display = "none";
    loadRooms();
    loadCustomerBookings();
    startAvailabilityRefresh();
  }
}

function logout() {
  currentUser = null;
  stopAvailabilityRefresh();
  localStorage.removeItem("currentUser");
  document.getElementById("auth-page").classList.add("active");
  document.getElementById("app-container").classList.remove("active");
  closeModal();
  closeEditModal();
}

window.addEventListener("DOMContentLoaded", () => {
  const saved = localStorage.getItem("currentUser");
  if (saved) {
    currentUser = JSON.parse(saved);
    showMainApp();
  }

  document.getElementById("check-in")?.addEventListener("change", calculateTotalCost);
  document.getElementById("check-out")?.addEventListener("change", calculateTotalCost);
  document.getElementById("booking-guests")?.addEventListener("input", calculateTotalCost);
  document.getElementById("min-price-range")?.addEventListener("input", handlePriceFilterChange);
  document.getElementById("max-price-range")?.addEventListener("input", handlePriceFilterChange);
  document.getElementById("location-filter")?.addEventListener("change", handleAdvancedFilterChange);
  document.getElementById("rating-filter")?.addEventListener("change", handleAdvancedFilterChange);
  document.getElementById("amenities-filter")?.addEventListener("change", handleAmenitiesFilterChange);
  document.getElementById("edit-room-id")?.addEventListener("change", () => {
    loadAvailabilityCalendar("edit");
    calculateEditTotalCost();
  });
  document.getElementById("edit-check-in")?.addEventListener("change", calculateEditTotalCost);
  document.getElementById("edit-check-out")?.addEventListener("change", calculateEditTotalCost);
  document.getElementById("edit-guests")?.addEventListener("input", calculateEditTotalCost);

  ["modal", "edit-modal", "success-modal", "review-modal"].forEach((id) => {
    document.getElementById(id)?.addEventListener("click", (event) => {
      if (event.target.id === id) hideModal(id);
    });
  });
});

async function fetchJson(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (currentUser?.user_id) {
    headers.set("X-User-Id", currentUser.user_id);
    headers.set("X-User-Role", currentUser.role || "customer");
  }

  const response = await fetch(url, { ...options, headers });
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || "Something went wrong.");
  return data;
}

function showModal(id) {
  document.getElementById(id)?.classList.add("active");
}

function hideModal(id) {
  document.getElementById(id)?.classList.remove("active");
}

function showToast(message, type = "success") {
  const existing = document.getElementById("app-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "app-toast";
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add("visible"));

  window.setTimeout(() => {
    toast.classList.remove("visible");
    window.setTimeout(() => toast.remove(), 220);
  }, 2400);
}

function switchCustomerTab(tabName, event) {
  document.querySelectorAll("#customer-dashboard .tab-content").forEach((tab) => tab.classList.remove("active"));
  document.querySelectorAll("#customer-dashboard .nav-btn").forEach((btn) => btn.classList.remove("active"));
  document.getElementById(`${tabName}-tab`).classList.add("active");
  event?.target.classList.add("active");
  if (tabName === "bookings") loadCustomerBookings();
  if (tabName === "wishlist") loadWishlist();
}

function switchAdminTab(tabName, event) {
  document.querySelectorAll("#admin-dashboard .tab-content").forEach((tab) => tab.classList.remove("active"));
  document.querySelectorAll("#admin-dashboard .nav-btn").forEach((btn) => btn.classList.remove("active"));
  document.getElementById(`${tabName}-tab-admin`).classList.add("active");
  event?.target.classList.add("active");
  if (tabName === "analytics") loadAdminAnalytics();
  if (tabName === "bookings") loadAdminBookings();
  if (tabName === "customers") loadAdminCustomers();
  if (tabName === "rooms") loadAdminRooms();
}

function getToday() {
  return new Date().toISOString().split("T")[0];
}

function getTomorrow() {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  return tomorrow.toISOString().split("T")[0];
}

function formatCurrency(value) {
  return `Rs${Number(value || 0).toFixed(2)}`;
}

function formatDate(value) {
  return new Date(value).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function renderStars(rating) {
  const filled = Math.round(Number(rating || 0));
  return "★★★★★"
    .split("")
    .map((star, index) => `<span class="${index < filled ? "filled" : ""}">${star}</span>`)
    .join("");
}

function getFilteredRooms() {
  return allRooms;
}

function syncPriceFilterRange(bounds = roomFilterOptions.price_bounds) {
  const minSlider = document.getElementById("min-price-range");
  const maxSlider = document.getElementById("max-price-range");
  if (!minSlider || !maxSlider) return;

  const minBound = Number(bounds?.min ?? 0);
  const maxBound = Math.max(10000, Math.ceil(Number(bounds?.max ?? 10000) / 500) * 500);

  minSlider.min = String(minBound);
  minSlider.max = String(maxBound);
  maxSlider.min = String(minBound);
  maxSlider.max = String(maxBound);

  if (!roomFiltersInitialized) {
    roomSearchState.minPrice = minBound;
    roomSearchState.maxPrice = maxBound;
    roomFiltersInitialized = true;
  } else if (roomSearchState.maxPrice > maxBound) {
    roomSearchState.maxPrice = maxBound;
  }
  if (roomSearchState.minPrice < minBound) {
    roomSearchState.minPrice = minBound;
  }
  if (roomSearchState.minPrice > roomSearchState.maxPrice) {
    roomSearchState.minPrice = roomSearchState.maxPrice;
  }

  minPriceFilter = roomSearchState.minPrice;
  currentPriceFilter = roomSearchState.maxPrice;
  minSlider.value = String(roomSearchState.minPrice);
  maxSlider.value = String(roomSearchState.maxPrice);
  updatePriceFilterLabels();
}

function updatePriceFilterLabels() {
  const minLabel = document.getElementById("min-price-label");
  const maxLabel = document.getElementById("price-range-label");
  if (minLabel) {
    minLabel.textContent = `From ${formatCurrency(roomSearchState.minPrice)}`;
  }
  if (maxLabel) {
    const sliderMax = Number(document.getElementById("max-price-range")?.max || roomSearchState.maxPrice);
    maxLabel.textContent =
      roomSearchState.maxPrice >= sliderMax
        ? `Showing rooms up to ${formatCurrency(roomSearchState.maxPrice)}`
        : `Up to ${formatCurrency(roomSearchState.maxPrice)}`;
  }
}

function handlePriceFilterChange() {
  const minSlider = document.getElementById("min-price-range");
  const maxSlider = document.getElementById("max-price-range");
  if (!minSlider || !maxSlider) return;

  let nextMin = Number(minSlider.value);
  let nextMax = Number(maxSlider.value);
  if (nextMin > nextMax) {
    if (document.activeElement === minSlider) {
      nextMax = nextMin;
      maxSlider.value = String(nextMax);
    } else {
      nextMin = nextMax;
      minSlider.value = String(nextMin);
    }
  }

  roomSearchState.minPrice = nextMin;
  roomSearchState.maxPrice = nextMax;
  minPriceFilter = nextMin;
  currentPriceFilter = nextMax;
  roomSearchState.page = 1;
  updatePriceFilterLabels();
  loadRooms();
}

function handleAdvancedFilterChange() {
  roomSearchState.location = document.getElementById("location-filter")?.value || "";
  roomSearchState.rating = document.getElementById("rating-filter")?.value || "";
  roomSearchState.page = 1;
  loadRooms();
}

function handleAmenitiesFilterChange() {
  roomSearchState.amenities = Array.from(document.querySelectorAll('#amenities-filter input:checked')).map((input) => input.value);
  roomSearchState.page = 1;
  loadRooms();
}

function populateAdvancedFilters(filters) {
  roomFilterOptions = filters || roomFilterOptions;
  const locationSelect = document.getElementById("location-filter");
  const amenitiesContainer = document.getElementById("amenities-filter");

  if (locationSelect) {
    locationSelect.innerHTML = `<option value="">All locations</option>${(roomFilterOptions.locations || [])
      .map((location) => `<option value="${location}">${location}</option>`)
      .join("")}`;
    locationSelect.value = roomSearchState.location;
  }

  if (amenitiesContainer) {
    amenitiesContainer.innerHTML = (roomFilterOptions.amenities || [])
      .map(
        (amenity) => `
          <label class="amenity-pill">
            <input type="checkbox" value="${amenity}" ${roomSearchState.amenities.includes(amenity) ? "checked" : ""}>
            <span>${amenity}</span>
          </label>`
      )
      .join("");
  }

  const ratingSelect = document.getElementById("rating-filter");
  if (ratingSelect) {
    ratingSelect.value = roomSearchState.rating;
  }
}

function renderRoomsPagination() {
  const container = document.getElementById("rooms-pagination");
  if (!container) return;

  if ((roomPagination.total_pages || 1) <= 1) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
    <button type="button" class="btn-secondary pagination-btn" onclick="changeRoomsPage(${roomPagination.page - 1})" ${roomPagination.page <= 1 ? "disabled" : ""}>Previous</button>
    <p class="pagination-copy">Page ${roomPagination.page} of ${roomPagination.total_pages}</p>
    <button type="button" class="btn-primary pagination-btn" onclick="changeRoomsPage(${roomPagination.page + 1})" ${roomPagination.page >= roomPagination.total_pages ? "disabled" : ""}>Next</button>
  `;
}

function changeRoomsPage(page) {
  if (page < 1 || page > roomPagination.total_pages) return;
  roomSearchState.page = page;
  loadRooms();
}

function resetRoomSearch() {
  roomSearchState.page = 1;
  roomSearchState.location = "";
  roomSearchState.rating = "";
  roomSearchState.amenities = [];
  roomSearchState.minPrice = Number(roomFilterOptions.price_bounds?.min ?? 0);
  roomSearchState.maxPrice = Math.max(10000, Number(roomFilterOptions.price_bounds?.max ?? 10000));
  syncPriceFilterRange(roomFilterOptions.price_bounds);
  populateAdvancedFilters(roomFilterOptions);
  loadRooms();
}

function toggleRoomComparison(roomId) {
  const numericId = Number(roomId);
  if (selectedCompareRoomIds.includes(numericId)) {
    selectedCompareRoomIds = selectedCompareRoomIds.filter((id) => id !== numericId);
  } else {
    if (selectedCompareRoomIds.length >= 3) {
      alert("You can compare up to 3 rooms at a time.");
      return;
    }
    selectedCompareRoomIds = [...selectedCompareRoomIds, numericId];
  }
  updateComparisonPanel();
  renderRooms();
}

function clearRoomComparison() {
  selectedCompareRoomIds = [];
  updateComparisonPanel();
  renderRooms();
}

function toggleComparisonPanel(forceState) {
  const panel = document.getElementById("comparison-panel");
  if (!panel) return;
  const shouldShow =
    typeof forceState === "boolean" ? forceState : !panel.classList.contains("active");
  panel.classList.toggle("active", shouldShow);
  if (shouldShow) {
    updateComparisonPanel();
  }
}

function updateComparisonPanel() {
  const compareCount = document.getElementById("compare-count");
  const comparisonContent = document.getElementById("comparison-content");
  const selectedRooms = allRooms.filter((room) => selectedCompareRoomIds.includes(Number(room.room_id)));

  if (compareCount) {
    compareCount.textContent = selectedRooms.length
      ? `${selectedRooms.length} room${selectedRooms.length > 1 ? "s" : ""} selected for comparison`
      : "No rooms selected for comparison";
  }

  if (!comparisonContent) return;

  if (!selectedRooms.length) {
    comparisonContent.innerHTML = `<p class="comparison-empty">Choose up to 3 rooms to compare price, capacity, and amenities.</p>`;
    return;
  }

  const rows = [
    { label: "Room Type", render: (room) => room.room_type },
    { label: "Price", render: (room) => `${formatCurrency(room.price)} / night` },
    { label: "Capacity", render: (room) => `${room.capacity} guest${room.capacity > 1 ? "s" : ""}` },
    { label: "Amenities", render: (room) => room.amenities || "Standard" },
    { label: "Availability", render: (room) => getAvailabilityIndicator(room).text },
  ];

  comparisonContent.innerHTML = `
    <div class="comparison-table">
      <div class="comparison-row comparison-top">
        <div class="comparison-cell comparison-label">Feature</div>
        ${selectedRooms.map((room) => `<div class="comparison-cell comparison-room">${room.room_type}</div>`).join("")}
      </div>
      ${rows
        .map(
          (row) => `
        <div class="comparison-row">
          <div class="comparison-cell comparison-label">${row.label}</div>
          ${selectedRooms.map((room) => `<div class="comparison-cell">${row.render(room)}</div>`).join("")}
        </div>`
        )
        .join("")}
    </div>
  `;
}

function renderRooms() {
  const rooms = getFilteredRooms();
  updateRoomHighlights(rooms);
  let output = "";
  rooms.forEach((room) => {
    const bookingPercentage = room.max_bookings ? ((room.booking_count / room.max_bookings) * 100).toFixed(0) : 0;
    const availability = getAvailabilityIndicator(room);
    const isSelectedForCompare = selectedCompareRoomIds.includes(Number(room.room_id));
    const similarRooms = !room.is_available ? getSimilarRooms(room, allRooms, { guests: room.capacity }) : [];
    const tier = getRoomTier(room);
    const featureList = getRoomFeatureList(room);
    const topRated = isTopRatedRoom(room);
    output += `
      <div class="room">
        <div class="room-visual" style="background-image:url('${room.image_url || ""}')">
          <div class="room-visual-overlay">
            <span class="room-tier">${topRated ? "Top Rated" : tier}</span>
            <span class="room-view">${room.view_type || "City"} View</span>
          </div>
        </div>
        <div class="room-card-top">
          <div>
            <h3>${room.room_type}</h3>
            <p class="room-subtitle">Floor ${room.floor_level || 1} • Sleeps ${room.capacity}</p>
          </div>
          <label class="compare-toggle">
            <input type="checkbox" ${isSelectedForCompare ? "checked" : ""} onchange="toggleRoomComparison(${room.room_id})">
            <span>Compare</span>
          </label>
        </div>
        <p class="room-price">${formatCurrency(room.price)}<small> per night</small></p>
        <div class="room-rating-row">
          <div class="stars">${renderStars(room.rating)}</div>
          <p>${Number(room.rating || 0).toFixed(1)} / 5 ${Number(room.total_reviews || 0) ? `• ${room.total_reviews} review${room.total_reviews > 1 ? "s" : ""}` : "• New stay"}</p>
        </div>
        <p class="room-description">${room.description || "A refined room crafted for comfort and memorable stays."}</p>
        <div class="room-meta-grid">
          <p class="room-capacity"><strong>Capacity</strong><span>${room.capacity} ${room.capacity > 1 ? "guests" : "guest"}</span></p>
          <p class="room-capacity"><strong>Location</strong><span>${room.location || "Main Wing"}</span></p>
          <p class="room-capacity"><strong>View</strong><span>${room.view_type || "City"}</span></p>
          <p class="room-capacity"><strong>Rating</strong><span>${Number(room.rating || 0).toFixed(1)} / 5</span></p>
        </div>
        <div class="room-feature-chips">
          ${featureList.map((feature) => `<span class="feature-chip">${feature}</span>`).join("")}
        </div>
        <p class="room-amenities">${room.amenities || "Standard amenities"}</p>
        <span class="status ${room.is_available ? "available" : "full"}">${room.is_available ? "Available" : "Full"}</span>
        <p class="availability-indicator ${availability.className}">${availability.text}</p>
        <div class="booking-count">
          <span>${room.available_slots}</span> slots available out of ${room.max_bookings}
          <div style="width:100%;height:6px;background:#e8eef5;border-radius:3px;margin-top:4px;overflow:hidden;">
            <div style="width:${bookingPercentage}%;height:100%;background:linear-gradient(90deg,#e74c3c,#c0392b);"></div>
          </div>
        </div>
        <button type="button" class="btn-primary btn-book" onclick="openModal(${room.room_id})" ${!room.is_available ? "disabled" : ""}>
          ${room.is_available ? "Book Now" : "Fully Booked"}
        </button>
        <button type="button" class="btn-secondary btn-wishlist" onclick="toggleWishlist(${room.room_id})" id="wishlist-btn-${room.room_id}">
          <i class="fas fa-heart"></i> Add to Wishlist
        </button>
        ${
          similarRooms.length
            ? `
          <div class="suggestion-group inline">
            <p class="suggestion-copy">Similar available rooms</p>
            <div class="suggestion-grid compact">
              ${similarRooms
                .map((similarRoom) =>
                  createSuggestionCard(
                    similarRoom,
                    "View & Book",
                    `openModal(${similarRoom.room_id})`
                  )
                )
                .join("")}
            </div>
          </div>`
            : ""
        }
      </div>`;
  });
  document.getElementById("rooms").innerHTML = output || "<p>No rooms match the current search filters.</p>";
}

function startOfToday() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
}

function startAvailabilityRefresh() {
  stopAvailabilityRefresh();
  availabilityRefreshTimer = window.setInterval(() => {
    if (currentUser?.role === "customer") {
      loadRooms(true);
    }
  }, 20000);
}

function stopAvailabilityRefresh() {
  if (availabilityRefreshTimer) {
    window.clearInterval(availabilityRefreshTimer);
    availabilityRefreshTimer = null;
  }
}

function getAvailabilityIndicator(room) {
  if (!room.is_available || room.available_slots <= 0) {
    return { text: "Sold out right now", className: "danger" };
  }
  if (room.available_slots === 1) {
    return { text: "Only 1 room left", className: "urgent" };
  }
  if (room.available_slots <= 3) {
    return { text: `Only ${room.available_slots} rooms left`, className: "urgent" };
  }
  return { text: `${room.available_slots} rooms available`, className: "stable" };
}

function getAmenityList(room) {
  return String(room.amenities || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function getAmenityOverlapScore(baseRoom, candidateRoom) {
  const baseAmenities = getAmenityList(baseRoom);
  const candidateAmenities = new Set(getAmenityList(candidateRoom));
  return baseAmenities.filter((item) => candidateAmenities.has(item)).length;
}

function getSimilarRooms(baseRoom, rooms, options = {}) {
  const { guests = baseRoom.capacity || 1, upgradesOnly = false } = options;
  return rooms
    .filter((room) => Number(room.room_id) !== Number(baseRoom.room_id))
    .filter((room) => room.is_available)
    .filter((room) => Number(room.capacity) >= Number(guests))
    .filter((room) => (upgradesOnly ? Number(room.price) > Number(baseRoom.price) : true))
    .map((room) => ({
      room,
      priceGap: Math.abs(Number(room.price) - Number(baseRoom.price)),
      amenityScore: getAmenityOverlapScore(baseRoom, room),
      capacityGap: Math.abs(Number(room.capacity) - Number(baseRoom.capacity || guests)),
    }))
    .filter((item) => item.amenityScore > 0 || item.priceGap <= 2500)
    .sort((a, b) => {
      if (upgradesOnly && a.room.price !== b.room.price) {
        return Number(a.room.price) - Number(b.room.price);
      }
      if (a.amenityScore !== b.amenityScore) {
        return b.amenityScore - a.amenityScore;
      }
      if (a.priceGap !== b.priceGap) {
        return a.priceGap - b.priceGap;
      }
      return a.capacityGap - b.capacityGap;
    })
    .slice(0, 3)
    .map((item) => item.room);
}

function createSuggestionCard(room, actionLabel, actionHandler) {
  return `
    <div class="suggestion-card">
      <h4>${room.room_type}</h4>
      <p>${formatCurrency(room.price)} per night</p>
      <p>Capacity: ${room.capacity} ${room.capacity > 1 ? "guests" : "guest"}</p>
      <p>${room.amenities || "Standard amenities"}</p>
      <button type="button" class="btn-secondary" onclick="${actionHandler}">${actionLabel}</button>
    </div>
  `;
}

function getRoomTier(room) {
  const price = Number(room.price || 0);
  if (price >= 10000) return "Presidential";
  if (price >= 8000) return "Signature";
  if (price >= 6000) return "Suite";
  if (price >= 4500) return "Premium";
  return "Classic";
}

function isTopRatedRoom(room) {
  return Number(room.rating || 0) >= 4.8 && Number(room.total_reviews || 0) >= 1;
}

function getRoomFeatureList(room) {
  return String(room.features || room.amenities || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 4);
}

function updateRoomHighlights(roomsToShow) {
  const roomCount = document.getElementById("room-count-highlight");
  if (roomCount) {
    roomCount.textContent = `${roomPagination.total_items} curated stay${roomPagination.total_items > 1 ? "s" : ""}`;
  }

  const sectionCopy = document.querySelector(".room-heading .section-copy");
  if (sectionCopy) {
    sectionCopy.textContent = roomPagination.total_items === roomsToShow.length && roomPagination.page === 1
      ? "Filter by budget, compare options side by side, and open any room to continue booking."
      : `${roomPagination.total_items} room${roomPagination.total_items > 1 ? "s" : ""} match your current search.`;
  }

  const resultsSummary = document.getElementById("results-summary");
  if (resultsSummary) {
    if (!roomPagination.total_items) {
      resultsSummary.textContent = "No rooms match the current filters.";
    } else {
      const start = (roomPagination.page - 1) * roomPagination.page_size + 1;
      const end = Math.min(start + roomsToShow.length - 1, roomPagination.total_items);
      resultsSummary.textContent = `Showing ${start}-${end} of ${roomPagination.total_items} rooms`;
    }
  }
}

function renderRoomReviews(roomId) {
  const summary = document.getElementById("room-review-summary");
  const list = document.getElementById("room-reviews-list");
  const room = allRooms.find((item) => Number(item.room_id) === Number(roomId));
  const reviewData = roomReviewsById[roomId];
  if (!summary || !list || !room) return;

  summary.innerHTML = `<span class="stars">${renderStars(room.rating)}</span> ${Number(room.rating || 0).toFixed(1)} / 5 • ${room.total_reviews || 0} review${Number(room.total_reviews || 0) === 1 ? "" : "s"}`;

  const reviews = reviewData?.reviews || [];
  if (!reviews.length) {
    list.innerHTML = `<p class="review-empty">No reviews yet. Be the first guest to share how this stay feels.</p>`;
    return;
  }

  list.innerHTML = reviews
    .map(
      (review) => `
        <article class="review-card">
          <div class="review-card-header">
            <div>
              <strong>${review.full_name}</strong>
              <p>${formatDate(review.created_at)}</p>
            </div>
            <div class="stars">${renderStars(review.rating)}</div>
          </div>
          <p>${review.review_text || "Loved the stay."}</p>
        </article>
      `
    )
    .join("");
}

async function fetchRoomReviews(roomId, { silent = false } = {}) {
  try {
    const data = await fetchJson(`${API_BASE_URL}/rooms/${roomId}/reviews`);
    roomReviewsById[roomId] = data;
    const room = allRooms.find((item) => Number(item.room_id) === Number(roomId));
    if (room) {
      room.rating = data.rating;
      room.total_reviews = data.total_reviews;
    }
    renderRoomReviews(roomId);
  } catch (error) {
    if (!silent) {
      const list = document.getElementById("room-reviews-list");
      if (list) list.innerHTML = `<p class="review-empty">${error.message}</p>`;
    }
  }
}

function renderUpgradeSuggestions(baseRoomId, guests, checkIn, checkOut) {
  const container = document.getElementById("upgrade-suggestions");
  if (!container) return;
  const baseRoom = allRooms.find((room) => Number(room.room_id) === Number(baseRoomId));
  if (!baseRoom) {
    container.innerHTML = "";
    return;
  }

  const upgrades = getSimilarRooms(baseRoom, allRooms, { guests, upgradesOnly: true });
  if (!upgrades.length) {
    container.innerHTML = `<p class="suggestion-empty">No upgrade suggestions right now. Your room is already a great fit.</p>`;
    return;
  }

  container.innerHTML = `
    <div class="suggestion-group">
      <h3>Smart Upgrade Suggestions</h3>
      <p class="suggestion-copy">Want a richer stay next time? These upgrades match your booking and add more amenities.</p>
      <div class="suggestion-grid">
        ${upgrades
          .map((room) =>
            createSuggestionCard(
              room,
              "Try This Upgrade",
              `openModal(${room.room_id}, { guests: ${guests}, checkIn: '${checkIn}', checkOut: '${checkOut}', message: 'We prefilled a premium suggestion for you. Adjust anything before confirming.' }); hideModal('success-modal');`
            )
          )
          .join("")}
      </div>
    </div>
  `;
}

function setCalendarMessage(mode, message, isError = false) {
  const element = document.getElementById(mode === "booking" ? "booking-calendar-message" : "edit-calendar-message");
  if (!element) return;
  element.textContent = message || "";
  element.classList.toggle("error", Boolean(message && isError));
}

function getCalendarConfig(mode) {
  return mode === "booking"
    ? {
        calendarId: "booking-calendar",
        checkInId: "check-in",
        checkOutId: "check-out",
        roomId: selectedRoom,
        excludeBookingId: null,
      }
    : {
        calendarId: "edit-calendar",
        checkInId: "edit-check-in",
        checkOutId: "edit-check-out",
        roomId: Number(document.getElementById("edit-room-id").value),
        excludeBookingId: Number(document.getElementById("edit-booking-id").value) || null,
      };
}

function dateRangeHasConflict(mode, checkIn, checkOut) {
  const blockedDates = availabilityState[mode].blockedDates || new Set();
  if (!checkIn || !checkOut) return false;
  let current = new Date(checkIn);
  const end = new Date(checkOut);
  while (current < end) {
    if (blockedDates.has(current.toISOString().split("T")[0])) {
      return current.toISOString().split("T")[0];
    }
    current.setDate(current.getDate() + 1);
  }
  return false;
}

function validateCalendarSelection(mode) {
  const { checkInId, checkOutId } = getCalendarConfig(mode);
  const checkIn = document.getElementById(checkInId).value;
  const checkOut = document.getElementById(checkOutId).value;

  if (!checkIn || !checkOut) {
    setCalendarMessage(mode, "Choose both check-in and check-out dates.");
    return false;
  }
  if (checkOut <= checkIn) {
    setCalendarMessage(mode, "Check-out must be after check-in.", true);
    return false;
  }

  const conflictDate = dateRangeHasConflict(mode, checkIn, checkOut);
  if (conflictDate) {
    setCalendarMessage(mode, `Selected dates conflict with an existing booking on ${formatDate(conflictDate)}.`, true);
    return false;
  }

  setCalendarMessage(mode, "Dates are available for booking.");
  return true;
}

async function loadAvailabilityCalendar(mode) {
  const { roomId, excludeBookingId } = getCalendarConfig(mode);
  if (!roomId) return;

  try {
    let url = `${API_BASE_URL}/rooms/${roomId}/availability?days=42`;
    if (excludeBookingId) {
      url += `&exclude_booking_id=${excludeBookingId}`;
    }
    const data = await fetchJson(url);
    availabilityState[mode].roomId = roomId;
    availabilityState[mode].excludeBookingId = excludeBookingId;
    availabilityState[mode].blockedDates = new Set(data.blocked_dates || []);
    availabilityState[mode].calendarDays = data.calendar || [];
    renderAvailabilityCalendar(mode);
    validateCalendarSelection(mode);
  } catch (error) {
    setCalendarMessage(mode, error.message, true);
  }
}

function renderAvailabilityCalendar(mode, calendarDays = availabilityState[mode].calendarDays || []) {
  const { calendarId, checkInId, checkOutId } = getCalendarConfig(mode);
  const container = document.getElementById(calendarId);
  if (!container) return;

  const selectedCheckIn = document.getElementById(checkInId).value;
  const selectedCheckOut = document.getElementById(checkOutId).value;

  container.innerHTML = calendarDays
    .map((day) => {
      const isSelectedStart = selectedCheckIn === day.date;
      const isSelectedEnd = selectedCheckOut === day.date;
      return `
        <button
          type="button"
          class="calendar-day ${day.is_blocked || day.is_past ? "blocked" : "available"} ${isSelectedStart || isSelectedEnd ? "selected" : ""}"
          data-mode="${mode}"
          data-date="${day.date}"
          ${day.is_blocked || day.is_past ? "disabled" : ""}
          onclick="selectCalendarDate('${mode}', '${day.date}')"
        >
          <span>${day.weekday}</span>
          <strong>${day.day}</strong>
        </button>
      `;
    })
    .join("");
}

function selectCalendarDate(mode, isoDate) {
  const { checkInId, checkOutId } = getCalendarConfig(mode);
  const checkInInput = document.getElementById(checkInId);
  const checkOutInput = document.getElementById(checkOutId);

  if (!checkInInput.value || (checkInInput.value && checkOutInput.value)) {
    checkInInput.value = isoDate;
    checkOutInput.value = "";
  } else if (isoDate <= checkInInput.value) {
    checkInInput.value = isoDate;
  } else {
    checkOutInput.value = isoDate;
  }

  if (mode === "booking") {
    renderAvailabilityCalendar("booking");
    validateCalendarSelection("booking");
    calculateTotalCost();
  } else {
    renderAvailabilityCalendar("edit");
    validateCalendarSelection("edit");
    calculateEditTotalCost();
  }
}

async function loadRooms(isSilent = false) {
  try {
    const params = new URLSearchParams({
      page: String(roomSearchState.page),
      page_size: String(roomSearchState.pageSize),
      min_price: String(roomSearchState.minPrice),
      max_price: String(roomSearchState.maxPrice),
    });
    if (roomSearchState.location) params.set("location", roomSearchState.location);
    if (roomSearchState.rating) params.set("rating", roomSearchState.rating);
    if (roomSearchState.amenities.length) params.set("amenities", roomSearchState.amenities.join(","));

    const data = await fetchJson(`${API_BASE_URL}/rooms?${params.toString()}`);
    allRooms = data.items || [];
    roomPagination = data.pagination || roomPagination;
    roomFilterOptions = data.filters || roomFilterOptions;
    selectedCompareRoomIds = selectedCompareRoomIds.filter((roomId) =>
      allRooms.some((room) => Number(room.room_id) === Number(roomId))
    );
    syncPriceFilterRange(roomFilterOptions.price_bounds);
    populateAdvancedFilters(roomFilterOptions);
    updateComparisonPanel();
    renderRooms();
    renderRoomsPagination();
    updateWishlistButtons(); // Update wishlist button states
  } catch (error) {
    if (!isSilent) {
      document.getElementById("rooms").innerHTML = `<p style="color:red;">Error: ${error.message}</p>`;
    }
  }
}

function openModal(roomId, prefill = null) {
  const room = allRooms.find((item) => Number(item.room_id) === Number(roomId));
  if (!room) return;
  selectedRoom = roomId;
  bookingPrefill = prefill;
  document.getElementById("check-in").min = getToday();
  document.getElementById("check-out").min = getTomorrow();
  document.getElementById("check-in").value = prefill?.checkIn || getToday();
  document.getElementById("check-out").value = prefill?.checkOut || getTomorrow();
  document.getElementById("booking-guests").value = prefill?.guests || 1;
  document.getElementById("booking-guests").max = room.capacity;
  document.getElementById("room-name").textContent = room.room_type;
  document.getElementById("room-price").textContent = `${formatCurrency(room.price)} per night`;
  document.getElementById("room-capacity").textContent = `Capacity: ${room.capacity} ${room.capacity > 1 ? "guests" : "guest"}`;
  document.getElementById("room-view").textContent = `Location: ${room.location || "Main Wing"} • ${room.view_type || "City"} View • Floor ${room.floor_level || 1}`;
  document.getElementById("room-rating").textContent = `Rating: ${Number(room.rating || 0).toFixed(1)} / 5 from ${room.total_reviews || 0} guest review${Number(room.total_reviews || 0) === 1 ? "" : "s"}`;
  document.getElementById("room-amenities").textContent = `Amenities: ${room.amenities || "Standard"}`;
  document.getElementById("room-description").textContent = room.description || "A refined room crafted for comfort and memorable stays.";
  setCalendarMessage(
    "booking",
    prefill?.message || `Choose your stay dates for ${room.room_type}.`
  );
  calculateTotalCost();
  loadAvailabilityCalendar("booking");
  renderRoomReviews(roomId);
  fetchRoomReviews(roomId, { silent: true });
  showModal("modal");
}

function closeModal() {
  hideModal("modal");
  selectedRoom = null;
  bookingPrefill = null;
  setCalendarMessage("booking", "");
  const list = document.getElementById("room-reviews-list");
  if (list) list.innerHTML = "";
}

function calculateTotalCost() {
  const checkIn = document.getElementById("check-in").value;
  const checkOut = document.getElementById("check-out").value;
  const room = allRooms.find((item) => Number(item.room_id) === Number(selectedRoom));
  if (!checkIn || !checkOut || !room) return;
  if (!validateCalendarSelection("booking")) {
    document.getElementById("total-cost").textContent = "";
    renderAvailabilityCalendar("booking");
    return;
  }
  const nights = Math.max(1, (new Date(checkOut) - new Date(checkIn)) / (1000 * 60 * 60 * 24));
  renderAvailabilityCalendar("booking");
  document.getElementById("total-cost").textContent = `Total Cost: ${formatCurrency(nights * Number(room.price))} (${nights} night${nights > 1 ? "s" : ""})`;
}

async function submitBooking(event) {
  event.preventDefault();
  if (!validateCalendarSelection("booking")) return;
  try {
    const payload = {
      room_id: selectedRoom,
      check_in: document.getElementById("check-in").value,
      check_out: document.getElementById("check-out").value,
      guests: Number(document.getElementById("booking-guests").value),
    };
    const data = await fetchJson(`${API_BASE_URL}/book`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    lastSuccessfulBookingId = data.booking_id;
    document.getElementById("success-message").innerHTML = `<p>Booking ID: #${data.booking_id}</p><p>Total Cost: ${formatCurrency(data.total_price)}</p>`;
    renderUpgradeSuggestions(payload.room_id, payload.guests, payload.check_in, payload.check_out);
    closeModal();
    showModal("success-modal");
    loadRooms();
    loadCustomerBookings();
  } catch (error) {
    alert("Booking failed: " + error.message);
  }
}

function closeSuccessModal() {
  const suggestions = document.getElementById("upgrade-suggestions");
  if (suggestions) suggestions.innerHTML = "";
  hideModal("success-modal");
}

async function downloadInvoice(bookingId) {
  try {
    const headers = new Headers();
    if (currentUser?.user_id) {
      headers.set("X-User-Id", currentUser.user_id);
      headers.set("X-User-Role", currentUser.role || "customer");
    }

    const response = await fetch(`${API_BASE_URL}/booking/${bookingId}/invoice`, {
      method: "GET",
      headers,
    });

    if (!response.ok) {
      let message = "Unable to download invoice.";
      try {
        const error = await response.json();
        message = error.message || message;
      } catch (_) {
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `booking-invoice-${bookingId}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    alert("Invoice download failed: " + error.message);
  }
}

function downloadLatestInvoice() {
  if (!lastSuccessfulBookingId) {
    alert("No recent booking invoice available yet.");
    return;
  }
  downloadInvoice(lastSuccessfulBookingId);
}

async function loadCustomerBookings() {
  try {
    currentBookings = await fetchJson(`${API_BASE_URL}/my-bookings`);
    displayCustomerBookings(currentBookings);
  } catch (error) {
    document.getElementById("customer-bookings").innerHTML = `<p style="color:red;">Error: ${error.message}</p>`;
  }
}

function displayCustomerBookings(bookings) {
  const container = document.getElementById("customer-bookings");
  if (!bookings.length) {
    container.innerHTML = `<div class="no-bookings"><p>You haven't made any bookings yet.</p></div>`;
    return;
  }
  const today = startOfToday();
  const upcoming = [];
  const past = [];
  const cancelled = [];

  bookings.forEach((booking) => {
    const isCancelled = booking.booking_status === "Cancelled" || booking.status === "Cancelled";
    const checkOut = new Date(booking.check_out_date);
    if (isCancelled) {
      cancelled.push(booking);
    } else if (checkOut < today) {
      past.push(booking);
    } else {
      upcoming.push(booking);
    }
  });

  let output = "";
  if (upcoming.length) {
    output += `<h3 class="booking-section-title">Upcoming and Active</h3>`;
    output += upcoming.map((booking) => createCustomerBookingCard(booking)).join("");
  }
  if (past.length) {
    output += `<h3 class="booking-section-title">Past Stays</h3>`;
    output += past.map((booking) => createCustomerBookingCard(booking, { isPast: true })).join("");
  }
  if (cancelled.length) {
    output += `<h3 class="booking-section-title">Cancelled Bookings</h3>`;
    output += cancelled.map((booking) => createCustomerBookingCard(booking)).join("");
  }

  container.innerHTML = output;
}

function createCustomerBookingCard(booking, options = {}) {
  const isCancelled = booking.booking_status === "Cancelled" || booking.status === "Cancelled";
  const isPast = Boolean(options.isPast);
  const canManage = !isCancelled && new Date(booking.check_in_date) > new Date(new Date().setHours(0, 0, 0, 0));
  const canReview = isPast && !booking.has_review;
  const history = Array.isArray(booking.modification_history) ? booking.modification_history : [];
  const historyHtml = history.length
    ? `<div class="booking-history"><strong>Modification History</strong>${history.map((entry) => `
        <div class="history-item">
          <p>${new Date(entry.changed_at).toLocaleString("en-IN")}</p>
          <p>${entry.previous.room_type} (${formatDate(entry.previous.check_in_date)} - ${formatDate(entry.previous.check_out_date)}) -> ${entry.updated.room_type} (${formatDate(entry.updated.check_in_date)} - ${formatDate(entry.updated.check_out_date)})</p>
          <p>Guests: ${entry.previous.guests} -> ${entry.updated.guests} | Total: ${formatCurrency(entry.previous.total_price)} -> ${formatCurrency(entry.updated.total_price)}</p>
        </div>`).join("")}</div>`
    : `<div class="booking-history"><strong>Modification History</strong><p>No changes yet.</p></div>`;

  return `
    <div class="booking-card ${isCancelled ? "cancelled" : ""}">
      <div class="booking-header">
        <div>
          <h3>${booking.room_type}</h3>
          <p style="margin-top:4px;font-size:12px;color:#7f8c8d;">#${booking.booking_id}</p>
        </div>
        <span class="booking-status ${isCancelled ? "cancelled" : "confirmed"}">${booking.booking_status || booking.status}</span>
      </div>
      <div class="booking-dates"><strong>${formatDate(booking.check_in_date)}</strong> -> <strong>${formatDate(booking.check_out_date)}</strong></div>
      <div class="booking-info">
        <p><strong>Guests:</strong> ${booking.guests}</p>
        <p><strong>Cancellation Policy:</strong> ${booking.cancellation_policy}</p>
        <p><strong>Refund Amount:</strong> ${formatCurrency(booking.refund_amount)}</p>
        ${isPast ? `<p><strong>Stay Status:</strong> Completed</p>` : ""}
        ${isCancelled ? `<p><strong>Cancellation Status:</strong> Cancelled</p>` : ""}
        ${booking.has_review ? `<p><strong>Your Review:</strong> ${booking.review_rating}/5</p>` : ""}
      </div>
      <p class="booking-price">${formatCurrency(booking.total_price)}</p>
      ${canManage ? `<div class="booking-actions"><button type="button" class="btn-primary" onclick="openEditBooking(${booking.booking_id})">Edit Booking</button><button type="button" class="btn-primary btn-cancel" onclick="cancelBooking(${booking.booking_id})">Cancel Booking</button></div>` : ""}
      <div class="booking-actions">
        <button type="button" class="btn-secondary" onclick="downloadInvoice(${booking.booking_id})">Download Invoice</button>
        <button type="button" class="btn-secondary" onclick="viewBookingHistory(${booking.booking_id})">View History</button>
        ${isPast ? `<button type="button" class="btn-primary" onclick="rebookStay(${booking.booking_id})">Rebook</button>` : ""}
        ${canReview ? `<button type="button" class="btn-primary" onclick="openReviewModal(${booking.booking_id})">Add Review</button>` : ""}
      </div>
      ${booking.has_review ? `<div class="booking-history"><strong>Your Review</strong><div class="history-item"><p>${booking.review_created_at ? new Date(booking.review_created_at).toLocaleString("en-IN") : ""}</p><p>${booking.review_text || "You rated this stay without a written review."}</p></div></div>` : ""}
      ${historyHtml}
    </div>`;
}

async function viewBookingHistory(bookingId) {
  try {
    const history = await fetchJson(`${API_BASE_URL}/booking-history/${bookingId}`);
    displayBookingHistory(bookingId, history);
  } catch (error) {
    alert(`Failed to load booking history: ${error.message}`);
  }
}

function displayBookingHistory(bookingId, history) {
  const timelineHtml = history.map(entry => {
    const timestamp = new Date(entry.created_at).toLocaleString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });

    let changesHtml = '';
    if (entry.previous_data && entry.new_data) {
      const prev = JSON.parse(entry.previous_data);
      const curr = JSON.parse(entry.new_data);

      const changes = [];

      if (prev.room_id !== curr.room_id) {
        changes.push(`Room changed from ${prev.room_id} to ${curr.room_id}`);
      }
      if (prev.check_in_date !== curr.check_in_date || prev.check_out_date !== curr.check_out_date) {
        changes.push(`Dates: ${prev.check_in_date} to ${prev.check_out_date} → ${curr.check_in_date} to ${curr.check_out_date}`);
      }
      if (prev.guest_count !== curr.guest_count) {
        changes.push(`Guests: ${prev.guest_count} → ${curr.guest_count}`);
      }
      if (prev.booking_status !== curr.booking_status) {
        changes.push(`Status: ${prev.booking_status} → ${curr.booking_status}`);
      }
      if (prev.total_price !== curr.total_price) {
        changes.push(`Price: ${formatCurrency(prev.total_price)} → ${formatCurrency(curr.total_price)}`);
      }

      changesHtml = changes.length > 0 ? `<div class="history-changes">${changes.join('<br>')}</div>` : '';
    }

    const actionIcon = getActionIcon(entry.action_type);
    const actionColor = getActionColor(entry.action_type);

    return `
      <div class="timeline-item">
        <div class="timeline-marker ${actionColor}">
          <i class="${actionIcon}"></i>
        </div>
        <div class="timeline-content">
          <div class="timeline-header">
            <h4>${formatActionType(entry.action_type)}</h4>
            <span class="timeline-timestamp">${timestamp}</span>
          </div>
          <div class="timeline-user">
            <span>by ${entry.user_name} (${entry.user_email})</span>
          </div>
          ${entry.note ? `<div class="timeline-note">${entry.note}</div>` : ''}
          ${changesHtml}
        </div>
      </div>
    `;
  }).join('');

  const modalHtml = `
    <div id="history-modal" class="modal">
      <div class="modal-content large-modal">
        <div class="modal-header">
          <h2>Booking History - #${bookingId}</h2>
          <span class="modal-close" onclick="closeHistoryModal()">&times;</span>
        </div>
        <div class="modal-body">
          <div class="timeline">
            ${timelineHtml || '<p>No history available for this booking.</p>'}
          </div>
        </div>
      </div>
    </div>
  `;

  // Remove existing modal if present
  const existingModal = document.getElementById('history-modal');
  if (existingModal) {
    existingModal.remove();
  }

  document.body.insertAdjacentHTML('beforeend', modalHtml);
  document.getElementById('history-modal').style.display = 'block';
}

function getActionIcon(actionType) {
  switch (actionType) {
    case 'created': return 'fas fa-plus-circle';
    case 'modified': return 'fas fa-edit';
    case 'cancelled': return 'fas fa-times-circle';
    case 'status_changed': return 'fas fa-exchange-alt';
    default: return 'fas fa-info-circle';
  }
}

function getActionColor(actionType) {
  switch (actionType) {
    case 'created': return 'success';
    case 'modified': return 'warning';
    case 'cancelled': return 'danger';
    case 'status_changed': return 'info';
    default: return 'secondary';
  }
}

function formatActionType(actionType) {
  switch (actionType) {
    case 'created': return 'Booking Created';
    case 'modified': return 'Booking Modified';
    case 'cancelled': return 'Booking Cancelled';
    case 'status_changed': return 'Status Changed';
    default: return actionType.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
  }
}

function closeHistoryModal() {
  const modal = document.getElementById('history-modal');
  if (modal) {
    modal.style.display = 'none';
    modal.remove();
  }
}

async function ensureBookingOptions() {
  if (allRooms.length) return;
  allRooms = await fetchJson(`${API_BASE_URL}/booking-options`);
}

async function openEditBooking(bookingId) {
  try {
    await ensureBookingOptions();
    const booking = currentBookings.find((item) => Number(item.booking_id) === Number(bookingId));
    if (!booking) return;

    const select = document.getElementById("edit-room-id");
    select.innerHTML = allRooms.map((room) => `<option value="${room.room_id}">${room.room_type} - ${formatCurrency(room.price)} / night</option>`).join("");
    document.getElementById("edit-booking-id").value = booking.booking_id;
    document.getElementById("edit-room-id").value = booking.room_id;
    document.getElementById("edit-guests").value = booking.guests;
    document.getElementById("edit-check-in").value = booking.check_in_date;
    document.getElementById("edit-check-in").min = getToday();
    document.getElementById("edit-check-out").value = booking.check_out_date;
    document.getElementById("edit-check-out").min = getTomorrow();
    calculateEditTotalCost();
    loadAvailabilityCalendar("edit");
    showModal("edit-modal");
  } catch (error) {
    alert("Unable to load booking editor: " + error.message);
  }
}

function closeEditModal() {
  hideModal("edit-modal");
  setCalendarMessage("edit", "");
}

function calculateEditTotalCost() {
  const roomId = Number(document.getElementById("edit-room-id").value);
  const room = allRooms.find((item) => Number(item.room_id) === roomId);
  const checkIn = document.getElementById("edit-check-in").value;
  const checkOut = document.getElementById("edit-check-out").value;
  const guests = Number(document.getElementById("edit-guests").value || 1);
  if (!room || !checkIn || !checkOut) return;

  document.getElementById("edit-guests").max = room.capacity;
  document.getElementById("edit-room-capacity").textContent = `Capacity: ${room.capacity} ${room.capacity > 1 ? "guests" : "guest"}`;
  document.getElementById("edit-room-view").textContent = `Location: ${room.location || "Main Wing"} • ${room.view_type || "City"} View • Floor ${room.floor_level || 1}`;
  document.getElementById("edit-room-amenities").textContent = `Amenities: ${room.amenities || "Standard"}`;
  document.getElementById("edit-room-description").textContent = room.description || "A refined room crafted for comfort and memorable stays.";
  if (!validateCalendarSelection("edit")) {
    document.getElementById("edit-total-cost").textContent = "";
    renderAvailabilityCalendar("edit");
    return;
  }
  const nights = Math.max(1, (new Date(checkOut) - new Date(checkIn)) / (1000 * 60 * 60 * 24));
  const total = nights * Number(room.price);
  const capacityNote = guests > room.capacity ? ` Selected guests exceed capacity.` : "";
  renderAvailabilityCalendar("edit");
  document.getElementById("edit-total-cost").textContent = `Updated Total: ${formatCurrency(total)} (${nights} night${nights > 1 ? "s" : ""}).${capacityNote}`;
}

async function submitBookingUpdate(event) {
  event.preventDefault();
  if (!validateCalendarSelection("edit")) return;
  const bookingId = document.getElementById("edit-booking-id").value;
  const payload = {
    room_id: Number(document.getElementById("edit-room-id").value),
    guests: Number(document.getElementById("edit-guests").value),
    check_in: document.getElementById("edit-check-in").value,
    check_out: document.getElementById("edit-check-out").value,
  };

  try {
    const data = await fetchJson(`${API_BASE_URL}/booking/${bookingId}/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    alert(`Booking updated. New total: ${formatCurrency(data.total_price)}`);
    closeEditModal();
    loadCustomerBookings();
    loadRooms();
  } catch (error) {
    alert("Update failed: " + error.message);
  }
}

async function cancelBooking(bookingId) {
  if (!confirm("Are you sure you want to cancel this booking?")) return;
  try {
    const data = await fetchJson(`${API_BASE_URL}/cancel/${bookingId}`, { method: "POST", headers: { "Content-Type": "application/json" } });
    alert(`${data.message}\nPolicy: ${data.cancellation_policy}\nRefund: ${formatCurrency(data.refund_amount)}`);
    loadCustomerBookings();
    loadRooms();
  } catch (error) {
    alert("Cancellation failed: " + error.message);
  }
}

async function rebookStay(bookingId) {
  if (!allRooms.length) {
    await loadRooms();
  }
  const booking = currentBookings.find((item) => Number(item.booking_id) === Number(bookingId));
  if (!booking) return;

  const previousCheckIn = new Date(booking.check_in_date);
  const previousCheckOut = new Date(booking.check_out_date);
  const nights = Math.max(1, Math.round((previousCheckOut - previousCheckIn) / (1000 * 60 * 60 * 24)));
  const suggestedCheckIn = new Date();
  suggestedCheckIn.setHours(0, 0, 0, 0);
  suggestedCheckIn.setDate(suggestedCheckIn.getDate() + 1);
  const suggestedCheckOut = new Date(suggestedCheckIn);
  suggestedCheckOut.setDate(suggestedCheckOut.getDate() + nights);

  const roomsTabButton = document.querySelector('#customer-dashboard .nav-btn');
  switchCustomerTab("rooms", {
    target: roomsTabButton,
  });

  openModal(booking.room_id, {
    guests: booking.guests,
    checkIn: suggestedCheckIn.toISOString().split("T")[0],
    checkOut: suggestedCheckOut.toISOString().split("T")[0],
    message: `Rebooking your previous ${booking.room_type}. Adjust the dates or guests before confirming.`,
  });
}

function openReviewModal(bookingId) {
  document.getElementById("review-booking-id").value = bookingId;
  document.getElementById("review-rating").value = "";
  document.getElementById("review-text").value = "";
  showModal("review-modal");
}

function closeReviewModal() {
  hideModal("review-modal");
}

async function submitReview(event) {
  event.preventDefault();
  const bookingId = document.getElementById("review-booking-id").value;
  const rating = Number(document.getElementById("review-rating").value);
  const reviewText = document.getElementById("review-text").value.trim();

  try {
    const data = await fetchJson(`${API_BASE_URL}/booking/${bookingId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating, review_text: reviewText }),
    });
    alert(data.message);
    closeReviewModal();
    await loadCustomerBookings();
    await loadRooms();
    const booking = currentBookings.find((item) => Number(item.booking_id) === Number(bookingId));
    if (booking) {
      fetchRoomReviews(booking.room_id, { silent: true });
    }
  } catch (error) {
    alert("Review failed: " + error.message);
  }
}

async function loadAdminAnalytics() {
  try {
    const data = await fetchJson(`${API_BASE_URL}/admin/analytics`);

    // Update summary cards
    document.getElementById("total-revenue").textContent = formatCurrency(data.summary.total_revenue);
    document.getElementById("total-bookings").textContent = data.summary.total_bookings;
    document.getElementById("total-customers").textContent = data.summary.total_customers;
    document.getElementById("occupancy-rate").textContent = `${data.summary.occupancy_rate}%`;
    document.getElementById("cancellation-rate").textContent = `${data.summary.cancellation_rate}%`;

    // Create charts
    createRoomsChart(data.most_booked_rooms);
    createMonthlyChart(data.monthly_bookings);
    createDailyChart(data.daily_bookings);
    createRevenueChart(data.revenue_by_room);

    // Update tables
    updateRoomPerformanceTable(data.most_booked_rooms);
    updateBookingsTrendTable(data.monthly_bookings);

  } catch (error) {
    console.error('Analytics error:', error.message);
  }
}

// Chart creation functions
function createRoomsChart(roomsData) {
  const ctx = document.getElementById('rooms-chart').getContext('2d');
  const labels = roomsData.map(room => room.room_type);
  const data = roomsData.map(room => room.booking_count);

  analyticsCharts.rooms?.destroy();
  analyticsCharts.rooms = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Bookings',
        data: data,
        backgroundColor: 'rgba(54, 162, 235, 0.6)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            stepSize: 1
          }
        }
      },
      plugins: {
        legend: {
          display: false
        }
      }
    }
  });
}

function createMonthlyChart(monthlyData) {
  const ctx = document.getElementById('monthly-chart').getContext('2d');
  const labels = monthlyData.map(item => {
    const date = new Date(item.month + '-01');
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short' });
  }).reverse();
  const data = monthlyData.map(item => item.bookings).reverse();

  analyticsCharts.monthly?.destroy();
  analyticsCharts.monthly = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Monthly Bookings',
        data: data,
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        tension: 0.4,
        fill: true
      }]
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            stepSize: 1
          }
        }
      }
    }
  });
}

function createDailyChart(dailyData) {
  const ctx = document.getElementById('daily-chart').getContext('2d');
  const labels = dailyData.map(item => {
    const date = new Date(item.date);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }).reverse();
  const data = dailyData.map(item => item.bookings).reverse();

  analyticsCharts.daily?.destroy();
  analyticsCharts.daily = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Daily Bookings',
        data: data,
        backgroundColor: 'rgba(255, 159, 64, 0.6)',
        borderColor: 'rgba(255, 159, 64, 1)',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            stepSize: 1
          }
        }
      },
      plugins: {
        legend: {
          display: false
        }
      }
    }
  });
}

function createRevenueChart(revenueData) {
  const ctx = document.getElementById('revenue-chart').getContext('2d');
  const labels = revenueData.map(item => item.room_type);
  const data = revenueData.map(item => item.revenue);

  analyticsCharts.revenue?.destroy();
  analyticsCharts.revenue = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: [
          'rgba(255, 99, 132, 0.8)',
          'rgba(54, 162, 235, 0.8)',
          'rgba(255, 205, 86, 0.8)',
          'rgba(75, 192, 192, 0.8)',
          'rgba(153, 102, 255, 0.8)'
        ],
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: 'bottom'
        }
      }
    }
  });
}

// Table update functions
function updateRoomPerformanceTable(roomsData) {
  const tbody = document.querySelector('#room-performance-table tbody');
  tbody.innerHTML = roomsData.map(room => `
    <tr>
      <td>${room.room_type}</td>
      <td>${room.booking_count}</td>
      <td>${formatCurrency(room.total_revenue)}</td>
      <td>${room.booking_count > 0 ? formatCurrency(room.total_revenue / room.booking_count) : 'Rs0'}</td>
    </tr>
  `).join('');
}

function updateBookingsTrendTable(monthlyData) {
  const tbody = document.querySelector('#bookings-trend-table tbody');
  tbody.innerHTML = monthlyData.slice(0, 6).map(item => {
    const date = new Date(item.month + '-01');
    return `
      <tr>
        <td>${date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' })}</td>
        <td>${item.bookings}</td>
        <td>${formatCurrency(item.revenue)}</td>
      </tr>
    `;
  }).join('');
}

async function loadAdminBookings() {
  const search = document.getElementById("booking-search").value.trim();
  const status = document.getElementById("booking-status-filter").value;
  const params = new URLSearchParams();
  if (search) params.append("search", search);
  if (status) params.append("status", status);
  try {
    const data = await fetchJson(`${API_BASE_URL}/admin/bookings${params.toString() ? `?${params}` : ""}`);
    document.getElementById("admin-bookings").innerHTML = data.map((booking) => `
      <div class="booking-card ${booking.status === "Cancelled" ? "cancelled" : ""}">
        <div class="booking-header"><div><h3>${booking.room_type}</h3><p style="margin-top:4px;font-size:12px;color:#7f8c8d;">#${booking.booking_id}</p></div><span class="booking-status ${booking.status === "Cancelled" ? "cancelled" : "confirmed"}">${booking.status}</span></div>
        <div class="booking-info"><p><strong>Guest:</strong> ${booking.customer_name}</p><p><strong>Phone:</strong> ${booking.customer_phone}</p><p><strong>Email:</strong> ${booking.customer_email || "N/A"}</p></div>
        <div class="booking-dates">${formatDate(booking.check_in_date)} -> ${formatDate(booking.check_out_date)}</div>
        <p class="booking-price">${formatCurrency(booking.total_price)}</p>
      </div>`).join("");
  } catch (error) {
    document.getElementById("admin-bookings").innerHTML = `<p style="color:red;">Error: ${error.message}</p>`;
  }
}

async function loadAdminCustomers() {
  const search = document.getElementById("customer-search").value.trim();
  try {
    const data = await fetchJson(`${API_BASE_URL}/admin/customers${search ? `?search=${encodeURIComponent(search)}` : ""}`);
    document.getElementById("admin-customers").innerHTML = data.map((customer) => `
      <div class="customer-card">
        <div class="customer-header"><div><h3>${customer.full_name}</h3><p style="margin-top:4px;font-size:12px;color:#7f8c8d;">ID: ${customer.user_id}</p></div></div>
        <div class="customer-info"><p><strong>Email:</strong> ${customer.email}</p><p><strong>Phone:</strong> ${customer.phone}</p><p><strong>Bookings:</strong> ${customer.booking_count}</p><p><strong>Total Spent:</strong> ${formatCurrency(customer.total_spent)}</p></div>
      </div>`).join("");
  } catch (error) {
    document.getElementById("admin-customers").innerHTML = `<p style="color:red;">Error: ${error.message}</p>`;
  }
}

async function loadAdminRooms() {
  try {
    const rooms = await fetchJson(`${API_BASE_URL}/admin/rooms`);
    document.getElementById("admin-rooms").innerHTML = rooms.map((room) => `
      <div class="room admin-room-card" role="button" tabindex="0" onclick="openAdminRoomModal(${room.room_id})" onkeydown="handleAdminRoomKeydown(event, ${room.room_id})">
        <h3>${room.room_type}</h3>
        <p class="room-price">${formatCurrency(room.price)}<small> per night</small></p>
        <p class="room-capacity">Capacity: ${room.capacity}</p>
        <p class="room-amenities">${room.amenities || "Standard"}</p>
        <p style="font-size:12px;color:#7f8c8d;margin-top:8px;"><strong>Bookings:</strong> ${room.booking_count} / ${room.max_bookings}</p>
        <button type="button" class="btn-secondary admin-room-action">View Details</button>
      </div>`).join("");
  } catch (error) {
    document.getElementById("admin-rooms").innerHTML = `<p style="color:red;">Error: ${error.message}</p>`;
  }
}

function handleAdminRoomKeydown(event, roomId) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openAdminRoomModal(roomId);
  }
}

async function openAdminRoomModal(roomId) {
  try {
    const rooms = await fetchJson(`${API_BASE_URL}/admin/rooms`);
    const room = rooms.find((item) => Number(item.room_id) === Number(roomId));
    if (!room) return;

    document.getElementById("admin-room-name").textContent = room.room_type;
    document.getElementById("admin-room-price").textContent = `${formatCurrency(room.price)} per night`;
    document.getElementById("admin-room-capacity").textContent = `Capacity: ${room.capacity}`;
    document.getElementById("admin-room-location").textContent = `Location: ${room.location || "Main Wing"} • ${room.view_type || "City"} View`;
    document.getElementById("admin-room-rating").textContent = `Rating: ${Number(room.rating || 0).toFixed(1)} / 5`;
    document.getElementById("admin-room-bookings").textContent = `Bookings: ${room.booking_count} / ${room.max_bookings}`;
    document.getElementById("admin-room-amenities").textContent = `Amenities: ${room.amenities || "Standard"}`;
    document.getElementById("admin-room-description").textContent = room.description || "No detailed description available for this room yet.";
    showModal("admin-room-modal");
  } catch (error) {
    showToast(`Unable to open room details: ${error.message}`, "error");
  }
}

function closeAdminRoomModal() {
  hideModal("admin-room-modal");
}

// Wishlist functionality
async function loadWishlist() {
  try {
    const wishlistItems = await fetchJson(`${API_BASE_URL}/wishlist`);
    const wishlistContainer = document.getElementById("customer-wishlist");

    if (!wishlistItems.length) {
      wishlistContainer.innerHTML = `<p class="empty-state">Your wishlist is empty. Start exploring rooms to add some!</p>`;
      return;
    }

    wishlistContainer.innerHTML = wishlistItems.map((item) => `
      <div class="wishlist-item">
        <div class="wishlist-item-image" style="background-image:url('${item.image_url || ""}')"></div>
        <div class="wishlist-item-content">
          <div class="wishlist-item-header">
            <h3>${item.room_type}</h3>
            <button type="button" class="btn-remove-wishlist" onclick="removeFromWishlist(${item.room_id})" title="Remove from wishlist">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <p class="wishlist-item-price">${formatCurrency(item.price)}<small> per night</small></p>
          <div class="wishlist-item-meta">
            <span>Sleeps ${item.capacity}</span>
            <span>${item.location || "Main Wing"}</span>
            <span>${item.view_type || "City"} View</span>
          </div>
          <p class="wishlist-item-description">${item.description || "A refined room crafted for comfort and memorable stays."}</p>
          <div class="wishlist-item-rating">
            <div class="stars">${renderStars(item.rating)}</div>
            <span>${Number(item.rating || 0).toFixed(1)} / 5</span>
          </div>
          <button type="button" class="btn-primary" onclick="openModal(${item.room_id})">
            Book Now
          </button>
        </div>
      </div>
    `).join("");
  } catch (error) {
    document.getElementById("customer-wishlist").innerHTML = `<p style="color:red;">Error loading wishlist: ${error.message}</p>`;
  }
}

async function toggleWishlist(roomId) {
  const button = document.getElementById(`wishlist-btn-${roomId}`);
  if (!button) return;
  const icon = button.querySelector('i');

  try {
    // Check current status
    const status = await fetchJson(`${API_BASE_URL}/wishlist/${roomId}/status`);
    const isInWishlist = status.in_wishlist;

    if (isInWishlist) {
      // Remove from wishlist
      await fetchJson(`${API_BASE_URL}/wishlist/${roomId}`, { method: 'DELETE' });
      icon.className = 'fas fa-heart';
      button.innerHTML = '<i class="fas fa-heart"></i> Add to Wishlist';
      button.className = 'btn-secondary btn-wishlist';
      showToast('Removed from wishlist', 'success');
    } else {
      // Add to wishlist
      await fetchJson(`${API_BASE_URL}/wishlist/${roomId}`, { method: 'POST' });
      icon.className = 'fas fa-heart';
      button.innerHTML = '<i class="fas fa-heart"></i> Remove from Wishlist';
      button.className = 'btn-primary btn-wishlist';
      showToast('Added to wishlist', 'success');
    }

    // Refresh wishlist if currently viewing it
    if (document.getElementById('wishlist-tab').classList.contains('active')) {
      loadWishlist();
    }
  } catch (error) {
    showToast(`Error: ${error.message}`, 'error');
  }
}

async function removeFromWishlist(roomId) {
  try {
    await fetchJson(`${API_BASE_URL}/wishlist/${roomId}`, { method: 'DELETE' });
    showToast('Removed from wishlist', 'success');
    loadWishlist(); // Refresh the wishlist display
  } catch (error) {
    showToast(`Error: ${error.message}`, 'error');
  }
}

async function updateWishlistButtons() {
  if (!currentUser || currentUser.role !== 'customer') return;

  try {
    const wishlistItems = await fetchJson(`${API_BASE_URL}/wishlist`);
    const wishlistRoomIds = new Set(wishlistItems.map(item => item.room_id));

    // Update all wishlist buttons
    document.querySelectorAll('.btn-wishlist').forEach(button => {
      const roomId = button.id.replace('wishlist-btn-', '');
      const isInWishlist = wishlistRoomIds.has(Number(roomId));

      const icon = button.querySelector('i');
      if (isInWishlist) {
        icon.className = 'fas fa-heart';
        button.innerHTML = '<i class="fas fa-heart"></i> Remove from Wishlist';
        button.className = 'btn-primary btn-wishlist';
      } else {
        icon.className = 'fas fa-heart';
        button.innerHTML = '<i class="fas fa-heart"></i> Add to Wishlist';
        button.className = 'btn-secondary btn-wishlist';
      }
    });
  } catch (error) {
    console.error('Error updating wishlist buttons:', error);
  }
}
