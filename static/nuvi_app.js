// Nuvi Jobs Admin Dashboard - App Logic

document.addEventListener("DOMContentLoaded", () => {
  let tariffChart = null;
  let revenueChart = null;
  let allVacancies = [];

  // DOM Elements
  const turnoverVal = document.getElementById("turnoverVal");
  const totalVacanciesVal = document.getElementById("totalVacanciesVal");
  const pendingVal = document.getElementById("pendingVal");
  const totalUsersVal = document.getElementById("totalUsersVal");
  const submissionsBody = document.getElementById("submissionsBody");
  const refreshBtn = document.getElementById("refreshBtn");
  const detailModal = document.getElementById("detailModal");
  const closeModalBtn = document.getElementById("closeModalBtn");
  const modalBody = document.getElementById("modalBody");

  // Fetch Stats from API
  async function fetchStats() {
    // Spin refresh button
    refreshBtn.classList.add("spinning");
    try {
      const response = await fetch("/api/nuvi/stats");
      const data = await response.json();
      
      if (data && !data.error) {
        updateMetrics(data);
        updateTable(data.recent_vacancies);
        updateCharts(data);
        allVacancies = data.recent_vacancies;
      } else {
        console.error("Stats fetch error:", data.error);
      }
    } catch (e) {
      console.error("Network error fetching stats:", e);
    } finally {
      setTimeout(() => {
        refreshBtn.classList.remove("spinning");
      }, 600);
    }
  }

  // Update Metric Card Values
  function updateMetrics(data) {
    turnoverVal.textContent = formatCurrency(data.total_turnover);
    totalVacanciesVal.textContent = data.total_vacancies.toLocaleString();
    pendingVal.textContent = data.total_pending.toLocaleString();
    totalUsersVal.textContent = data.total_users.toLocaleString();
  }

  // Populate Vacancies Table
  function updateTable(vacancies) {
    if (!vacancies || vacancies.length === 0) {
      submissionsBody.innerHTML = `
        <tr>
          <td colspan="5" class="loading-cell">Hozircha hech qanday ariza kelmagan.</td>
        </tr>
      `;
      return;
    }

    submissionsBody.innerHTML = "";
    vacancies.forEach(v => {
      const tr = document.createElement("tr");
      tr.dataset.id = v.id;
      tr.addEventListener("click", () => openDetail(v.id));

      const statusMap = {
        'draft': `<span class="badge status-draft">Qoralama</span>`,
        'pending_approval': `<span class="badge status-pending">Kutilmoqda</span>`,
        'approved': `<span class="badge status-approved">Tasdiqlangan</span>`,
        'posted': `<span class="badge status-posted">Yuborilgan</span>`,
        'rejected': `<span class="badge status-rejected">Rad etilgan</span>`
      };

      const payMap = {
        'paid': `<span class="badge status-paid">To'langan</span>`,
        'unpaid': `<span class="badge status-unpaid">To'lanmagan</span>`
      };

      const tariffMap = {
        'pro': `<span class="badge badge-pro">Pro</span>`,
        'premium': `<span class="badge badge-premium">Premium</span>`,
        'vip': `<span class="badge badge-vip">VIP</span>`
      };

      tr.innerHTML = `
        <td><strong>${v.title}</strong></td>
        <td>${v.company}</td>
        <td>${tariffMap[v.tariff] || v.tariff}</td>
        <td>${payMap[v.payment_status] || v.payment_status}</td>
        <td>${statusMap[v.status] || v.status}</td>
      `;
      submissionsBody.appendChild(tr);
    });
  }

  // Update Chart.js Charts
  function updateCharts(data) {
    // 1. Tariff Doughnut Chart
    const tCanvas = document.getElementById("tariffChart");
    if (tariffChart) tariffChart.destroy();
    
    const proCount = data.tariffs?.pro?.total || 0;
    const premiumCount = data.tariffs?.premium?.total || 0;
    const vipCount = data.tariffs?.vip?.total || 0;

    tariffChart = new Chart(tCanvas, {
      type: "doughnut",
      data: {
        labels: ["Pro", "Premium", "VIP"],
        datasets: [{
          data: [proCount, premiumCount, vipCount],
          backgroundColor: ["#718096", "#0066ff", "#8b5cf6"],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#718096',
              font: { family: 'Inter', size: 12 },
              padding: 15
            }
          }
        },
        cutout: "70%"
      }
    });

    // 2. Monthly Revenue Dynamics
    const rCanvas = document.getElementById("revenueChart");
    if (revenueChart) revenueChart.destroy();

    let labels = [];
    let values = [];

    if (data.monthly_dynamics && data.monthly_dynamics.length > 0) {
      labels = data.monthly_dynamics.map(d => formatMonth(d.month));
      values = data.monthly_dynamics.map(d => d.amount);
    } else {
      labels = ["Ma'lumot yo'q"];
      values = [0];
    }

    revenueChart = new Chart(rCanvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: "Tushum (so'm)",
          data: values,
          backgroundColor: "#00e676",
          borderRadius: 8,
          maxBarThickness: 40
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#718096', font: { family: 'Inter' } }
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.04)' },
            ticks: {
              color: '#718096',
              font: { family: 'Inter' },
              callback: function(value) {
                return value >= 1000 ? (value / 1000) + 'k' : value;
              }
            }
          }
        }
      }
    });
  }

  // Open Vacancy Detail Modal
  function openDetail(id) {
    const v = allVacancies.find(x => x.id === id);
    if (!v) return;

    const statusMap = {
      'draft': `<span class="badge status-draft">Qoralama</span>`,
      'pending_approval': `<span class="badge status-pending">Kutilmoqda</span>`,
      'approved': `<span class="badge status-approved">Tasdiqlangan</span>`,
      'posted': `<span class="badge status-posted">Yuborilgan</span>`,
      'rejected': `<span class="badge status-rejected">Rad etilgan</span>`
    };

    const payMap = {
      'paid': `<span class="badge status-paid">To'langan</span>`,
      'unpaid': `<span class="badge status-unpaid">To'lanmagan</span>`
    };

    const tariffMap = {
      'pro': `<span class="badge badge-pro">Pro</span>`,
      'premium': `<span class="badge badge-premium">Premium</span>`,
      'vip': `<span class="badge badge-vip">VIP</span>`
    };

    modalBody.innerHTML = `
      <div class="detail-row">
        <span class="detail-label">Ariza ID</span>
        <span class="detail-val">#${v.id}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Lavozim</span>
        <span class="detail-val"><strong>${v.title}</strong></span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Kompaniya</span>
        <span class="detail-val">${v.company}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Maosh / Ish haqi</span>
        <span class="detail-val" style="color:var(--success);font-weight:700">${v.salary}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Tarif</span>
        <span class="detail-val">${tariffMap[v.tariff] || v.tariff}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">To'lov Holati</span>
        <span class="detail-val">${payMap[v.payment_status] || v.payment_status}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Ariza Holati</span>
        <span class="detail-val">${statusMap[v.status] || v.status}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Kim kiritgan</span>
        <span class="detail-val">${v.user_name}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Sana</span>
        <span class="detail-val">${v.created_at}</span>
      </div>
    `;

    detailModal.classList.add("active");
  }

  // Close Modal Helpers
  closeModalBtn.addEventListener("click", () => {
    detailModal.classList.remove("active");
  });

  window.addEventListener("click", (e) => {
    if (e.target === detailModal) {
      detailModal.classList.remove("active");
    }
  });

  // Refresh Trigger
  refreshBtn.addEventListener("click", fetchStats);

  // Formatting helpers
  function formatCurrency(val) {
    return new Intl.NumberFormat('uz-UZ', { style: 'currency', currency: 'UZS', maximumFractionDigits: 0 }).format(val);
  }

  function formatMonth(dateStr) {
    if (!dateStr) return "";
    const parts = dateStr.split("-");
    const year = parts[0];
    const month = parseInt(parts[1]);
    const months = ["Yan", "Fev", "Mar", "Apr", "May", "Iyun", "Iyul", "Avg", "Sen", "Okt", "Noy", "Dek"];
    return `${months[month - 1]} ${year}`;
  }

  // Initialize
  fetchStats();
});
