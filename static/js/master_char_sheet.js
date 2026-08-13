function toggleCollapse(element) {
    const content = element.nextElementSibling;
    const chevron = element.querySelector('.chevron');
    content.classList.toggle('open');
    chevron.classList.toggle('open');
}
