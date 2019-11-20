# AMWA NMOS Template Specification

## GitHub Pages documentation

If you are reading this you are on the gh-pages branch, which is used to generate the documentation from the master and other branches, and from releases.  These are served at <https://amwa-tv.github.io/nmos-template/>.

## Generating the documentation

If you make any changes to the repo please do the following:

Clone this repo (if you haven't already), checkout the gh-pages branch:

``git checkout gh-pages``

Install build tools (raml2html, jsonlint, now installed locally):

``make build-tools``

Make the documentation:

``make``

This runs scripts to:

- clone the repo from AMWA's GitHub
- for each branch and release (with some exceptions) extract documentation, APIs and schemas
  - making HTML renders of the RAML APIs
- for each branch and release create indexes for the documentation, APIs and schemas
- make links to what will later be the HTML renders of the Markdown documentation

## Updating AMWA's GitHub

You can push the updated documentation to AMWA's GitHub with.

``make push``

Alternatively commit and push manually for more control of the commit message.

Admins must be to do this after merging PRs etc (until this is automated with CircleCI at some point).

This then triggers a build of the GitHub Pages. This happens on GitHub's servers, using Jekyll to render the HTML.  This includes rendering the Markdown content, but we have to do the RAML ourselves.  

To clean up:

``make clean``

To also remove the build tools:

``make distclean``

## Serving pages locally

See also <https://help.github.com/articles/setting-up-your-github-pages-site-locally-with-jekyll>

Install Bundler and Jekyll - af you have Ruby installed then:

``gem install bundler``

``bundle install``

Run server with:

``make server``

And browse to <http://127.0.0.1:4000>.

