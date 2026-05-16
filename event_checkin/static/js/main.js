window.appUtils = {
  formatDateTimeVN(dateTimeString) {
    if (!dateTimeString) return '';
    const date = new Date(dateTimeString);
    if (Number.isNaN(date.getTime())) return dateTimeString;
    return new Intl.DateTimeFormat('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(date);
  },
};
