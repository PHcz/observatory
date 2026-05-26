<div class="container"><slot /></div>

<style>
  .container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 80px 64px;
  }

  @media (max-width: 900px) {
    .container {
      padding: 48px 24px;
    }
  }
</style>
