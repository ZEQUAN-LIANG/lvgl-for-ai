  if (appManageButton) appManageButton.addEventListener("click", openAppManager);
  if (managerClose) managerClose.addEventListener("click", closeAppManager);
  if (managerRefresh) managerRefresh.addEventListener("click", loadManager);
  if (managerForm) managerForm.addEventListener("submit", createManagedApp);
  if (appManager) {
    appManager.addEventListener("click", function (event) {
      if (event.target === appManager) closeAppManager();
    });
  }
